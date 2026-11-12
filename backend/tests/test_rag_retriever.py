"""RAG 检索模块测试（SYS-01/SYS-02）。

不访问网络：embedding 一律注入 FakeEmbedder。
覆盖：分块规则、RRF 数学、索引构建与重建失效、混合检索增益、降级路径、
失败状态、级联清理、状态字典。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import hashlib
import uuid
from dataclasses import dataclass

import numpy as np
import pytest

from modules.retriever.chunking import CHUNKING_VERSION, build_chunks, text_hash_of
from modules.retriever.embedding import EmbeddingClient, EmbeddingError
from modules.retriever.hybrid import retrieve, retrieve_with_legacy_fallback
from modules.retriever.service import IndexService
from modules.retriever.tables import ChunkEmbedding, RagChunk, RagIndex
from modules.retriever.vectorstore import pack_vector, rank_chunks_by_cosine, rrf_fuse


# ---------- 夹具 ----------
@pytest.fixture()
def rag_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RAG_INDEXING_ENABLED", "0")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "bm25")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "16")  # 与 FakeEmbedder 维度一致

    import app.config

    app.config.get_settings.cache_clear()
    from app.database import Base, make_engine, session_factory_for

    import app.models  # noqa: F401  业务表注册
    import modules.retriever.tables  # noqa: F401  RAG 表注册

    engine = make_engine(tmp_path / "data" / "app.db")
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    yield factory
    engine.dispose()
    app.config.get_settings.cache_clear()


@dataclass
class Piece:
    id: str
    start_sec: float
    end_sec: float
    text: str


def seed_video(factory, *, attempt: int = 1, pieces=None, duration: float = 300.0) -> str:
    from app.models import Segment, Video

    video_id = str(uuid.uuid4())
    db = factory()
    try:
        video = Video(
            id=video_id,
            title="RAG 测试课程",
            status="ready",
            processing_mode="audio_only",
            duration_sec=duration,
            size_bytes=1000,
            created_at="2026-11-12T00:00:00Z",
            updated_at="2026-11-12T00:00:00Z",
            attempt=attempt,
            local_path="unused.mp4",
        )
        db.add(video)
        db.flush()  # 先落视频行，segments 外键才成立（无 relationship，无自动排序保证）
        for index, piece in enumerate(pieces or []):
            db.add(
                Segment(
                    id=piece.id,
                    video_id=video_id,
                    start_sec=piece.start_sec,
                    end_sec=piece.end_sec,
                    text=piece.text,
                )
            )
        db.commit()
    finally:
        db.close()
    return video_id


class FakeEmbedder(EmbeddingClient):
    """确定性假向量：按关键词归入语义簇，簇内加文本哈希微扰。

    簇 A：召回率/查全率/找出所有正例 → e0 方向
    簇 B：损失函数/梯度下降   → e1 方向
    无关键词 → 哈希伪随机方向
    """

    def __init__(self, dim: int = 16, *, error: str | None = None) -> None:
        self.dim = dim
        self.error = error
        self.calls = 0
        self.last_texts: list[str] = []

    def embed(self, texts, budget_seconds=None):  # noqa: ARG002 预算参数保持接口一致
        self.calls += 1
        self.last_texts.extend(texts)
        if self.error:
            raise EmbeddingError(self.error)
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        cluster = None
        for keyword, direction in (
            ("召回率", 0),
            ("查全率", 0),
            ("正样本", 0),
            ("找出所有正例", 0),
            ("损失函数", 1),
            ("梯度下降", 1),
        ):
            if keyword in text:
                cluster = direction
                break
        noise = np.zeros(self.dim, dtype=np.float64)
        if cluster is None:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            for index in range(self.dim):
                noise[index] = digest[index % len(digest)] / 255.0
            vector = noise + 0.01
        else:
            vector = np.zeros(self.dim, dtype=np.float64)
            vector[cluster] = 1.0
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            for index in range(self.dim):
                noise[index] = (digest[index % len(digest)] / 255.0 - 0.5) * 0.05
            vector = vector + noise
        norm = float(np.linalg.norm(vector))
        return (vector / norm).astype(np.float32).tolist()


# ---------- 分块 ----------
def test_chunker_respects_span_and_char_limits():
    pieces = [
        Piece(f"seg-{i}", start_sec=i * 4.0, end_sec=i * 4.0 + 4.0, text="字" * 70)
        for i in range(9)
    ]
    chunks = build_chunks(pieces)
    assert chunks, "应产生至少一个块"
    assert all(chunk.char_count <= 240 for chunk in chunks)
    for window in zip(chunks, chunks[1:]):
        assert window[1].start_sec >= window[0].end_sec - 1e-9
    ids = [segment_id for chunk in chunks for segment_id in chunk.segment_ids]
    assert ids == [piece.id for piece in pieces]
    assert all(chunk.text_hash == text_hash_of(chunk.text) for chunk in chunks)


def test_chunker_long_segment_stays_whole():
    long_text = "字" * 300
    pieces = [Piece("seg-big", 0.0, 20.0, long_text)]
    chunks = build_chunks(pieces)
    assert len(chunks) == 1
    assert chunks[0].text == long_text  # 不伪造拆分时间：整句成块
    assert chunks[0].segment_ids == ["seg-big"]


def test_chunker_deterministic_and_versioned():
    pieces = [Piece("seg-a", 0.0, 10.0, "召回率是分类评估的核心指标"), Piece("seg-b", 10.0, 20.0, "损失函数决定梯度方向")]
    first = build_chunks(pieces)
    second = build_chunks(list(reversed(pieces)))  # 输入顺序不影响最终分块
    assert [chunk.text_hash for chunk in first] == [chunk.text_hash for chunk in second]
    assert CHUNKING_VERSION == "chunks_v1"


# ---------- RRF ----------
def test_rrf_fusion_math():
    fused = rrf_fuse([["a", "b", "c"], ["b", "d"]], k=60)
    score = {"a": 1 / 61, "b": 1 / 61 + 1 / 62, "c": 1 / 63, "d": 1 / 62}
    expected = sorted(score, key=lambda item: (-score[item], ["a", "b", "c", "d"].index(item)))
    assert fused == expected
    assert fused[0] == "b"  # 两路都靠前，RRF 应排第一


def test_cosine_rank_skips_bad_rows():
    query = [1.0, 0.0]
    rows = [("good", pack_vector([0.6, 0.8])), ("orthogonal", pack_vector([0.0, 1.0])), ("bad", b"\x00\x00\x00\x00")]
    ranked, skipped = rank_chunks_by_cosine(query, rows)
    assert ranked[0] == "good"
    assert skipped == 1  # 坏数据跳过，不炸整次检索


# ---------- 索引生命周期 ----------
def _ready_video_pieces():
    return [
        Piece("seg-0", 0.0, 10.0, "这一节讲召回率，它衡量分类器找出所有正例的能力。"),
        Piece("seg-1", 10.0, 20.0, "梯度下降通过损失函数的梯度更新参数。"),
        Piece("seg-2", 20.0, 30.0, "召回率和查全率是同一概念的不同译法。"),
        Piece("seg-3", 30.0, 40.0, "损失函数的选择会影响模型训练的收敛速度。"),
    ]


def test_index_build_and_rebuild_invalidates_old(rag_env):
    video_id = seed_video(rag_env, pieces=_ready_video_pieces())
    service = IndexService(rag_env, embedder=FakeEmbedder())

    assert service.enqueue(rag_env(), video_id) is not None
    assert service.build_once() is True

    db = rag_env()
    try:
        row = db.query(RagIndex).filter_by(video_id=video_id).one()
        assert row.status == "ready"
        assert row.chunk_count > 0
        assert db.query(RagChunk).filter_by(video_id=video_id).count() == row.chunk_count
        assert db.query(ChunkEmbedding).count() == row.chunk_count
    finally:
        db.close()

    # 重试 → attempt 2：旧 attempt 的块与索引行全部作废
    db = rag_env()
    try:
        from app.models import Video

        video = db.get(Video, video_id)
        video.attempt = 2
        db.commit()
    finally:
        db.close()
    service.enqueue(rag_env(), video_id)
    assert service.build_once() is True

    db = rag_env()
    try:
        assert db.query(RagChunk).filter_by(video_id=video_id).count() > 0
        assert db.query(RagChunk).filter_by(video_id=video_id, attempt=1).count() == 0
        assert db.query(RagIndex).filter_by(video_id=video_id).count() == 1
        assert db.query(RagIndex).filter_by(video_id=video_id).one().attempt == 2
    finally:
        db.close()


def test_index_failure_records_error_and_keeps_video(rag_env):
    video_id = seed_video(rag_env, pieces=_ready_video_pieces())
    service = IndexService(rag_env, embedder=FakeEmbedder(error="EMBED_TIMEOUT"))
    service.enqueue(rag_env(), video_id)
    assert service.build_once() is True  # 构建"完成"但落 failed 终态

    db = rag_env()
    try:
        row = db.query(RagIndex).filter_by(video_id=video_id).one()
        assert row.status == "failed"
        assert "EMBED_TIMEOUT" in (row.last_error or "")
        assert db.query(RagChunk).filter_by(video_id=video_id).count() == 0
        from app.models import Video

        assert db.get(Video, video_id).status == "ready"  # 视频本体不受影响
    finally:
        db.close()


def test_delete_video_cascades_rag_rows(rag_env):
    from app.models import Video

    video_id = seed_video(rag_env, pieces=_ready_video_pieces())
    service = IndexService(rag_env, embedder=FakeEmbedder())
    service.enqueue(rag_env(), video_id)
    service.build_once()

    db = rag_env()
    try:
        video = db.get(Video, video_id)
        db.delete(video)
        db.commit()
        assert db.query(RagChunk).filter_by(video_id=video_id).count() == 0
        assert db.query(RagIndex).filter_by(video_id=video_id).count() == 0
        assert db.query(ChunkEmbedding).count() == 0
    finally:
        db.close()


def test_status_dict_shape(rag_env):
    video_id = seed_video(rag_env, pieces=_ready_video_pieces())
    service = IndexService(rag_env, embedder=FakeEmbedder())
    service.enqueue(rag_env(), video_id)
    service.build_once()
    db = rag_env()
    try:
        status = IndexService.get_status(db, video_id)
        assert status["index_status"] == "ready"
        assert status["attempt"] == 1
        assert status["chunk_count"] > 0
        assert status["embedding_configured"] is False  # 测试环境无密钥
        assert status["chunking_version"] == CHUNKING_VERSION
    finally:
        db.close()


# ---------- 混合检索 ----------
def test_hybrid_beats_bm25_on_paraphrase(rag_env):
    """真·同义改写：与原文零共享分词，只有向量路能找回；RRF 融合后第一。"""
    filler = "，" * 115  # 撑过 120 字下限，保证两段不合并成一块
    pieces = [
        Piece("seg-0", 0.0, 10.0, "召回率反映分类器找出所有正例能力。" + filler),
        Piece("seg-1", 25.0, 35.0, "梯度下降利用损失函数与梯度更新参数。" + filler),
    ]
    video_id = seed_video(rag_env, pieces=pieces)
    embedder = FakeEmbedder()
    service = IndexService(rag_env, embedder=embedder)
    service.enqueue(rag_env(), video_id)
    service.build_once()

    question = "如何评估模型把全部正样本找出来的本事"
    db = rag_env()
    try:
        assert db.query(RagChunk).filter_by(video_id=video_id).count() == 2, "两段应各自成块"
        hybrid = retrieve(db, video_id, question, mode="hybrid", embedder=embedder)
        assert hybrid.mode_used == "hybrid"
        assert hybrid.hits, "混合检索应命中改写题"
        assert hybrid.hits[0].segment_ids == ["seg-0"], "向量路应把语义簇 A 的块排第一"
        assert hybrid.diagnostics["vector_candidates"] >= 1
        first_calls = embedder.calls

        bm25 = retrieve(db, video_id, question, mode="bm25", embedder=embedder)
        assert bm25.mode_used == "bm25"
        assert bm25.hits == [], "零共享分词时 BM25 找不到"

        # 查询缓存：第二次同题不再调用接口
        again = retrieve(db, video_id, question, mode="hybrid", embedder=embedder)
        assert again.diagnostics["cache_hit"] is True
        assert embedder.calls == first_calls
    finally:
        db.close()


def test_embedding_error_falls_back_to_bm25(rag_env):
    pieces = _ready_video_pieces()
    video_id = seed_video(rag_env, pieces=pieces)
    embedder = FakeEmbedder()
    service = IndexService(rag_env, embedder=embedder)
    service.enqueue(rag_env(), video_id)
    service.build_once()

    db = rag_env()
    try:
        outcome = retrieve(
            db, video_id, "召回率", mode="hybrid", embedder=FakeEmbedder(error="EMBED_AUTH_ERROR")
        )
        assert outcome.mode_used == "bm25_fallback"
        assert outcome.diagnostics["retrieval_error"] == "EMBED_AUTH_ERROR"
        assert outcome.hits  # BM25 路仍给出结果
        assert any("召回率" in hit.text for hit in outcome.hits)
    finally:
        db.close()


def test_no_index_returns_fallback(rag_env):
    video_id = seed_video(rag_env, pieces=_ready_video_pieces())  # 未建索引
    db = rag_env()
    try:
        outcome = retrieve(db, video_id, "召回率", mode="hybrid", embedder=FakeEmbedder())
        assert outcome.mode_used == "bm25_fallback"
        assert outcome.diagnostics["reason"] == "index_not_ready"
        assert outcome.hits == []
    finally:
        db.close()


def test_legacy_fallback_uses_baseline_search(rag_env):
    from app.retrieval import search_segments as _  # 确认基线可导入

    video_id = seed_video(rag_env, pieces=_ready_video_pieces())  # 无索引
    pieces = _ready_video_pieces()
    db = rag_env()
    try:
        outcome = retrieve_with_legacy_fallback(
            db, video_id, "召回率", pieces, 40.0, mode="hybrid", embedder=FakeEmbedder()
        )
        assert outcome.mode_used == "bm25_fallback"
        assert outcome.diagnostics.get("legacy_fallback") is True
        assert outcome.hits  # 基线 A 的 60 秒窗命中
        # 基线按 60 秒窗分块：四段都在第 0 窗，整窗一个块返回
        assert outcome.hits[0].segment_ids == ["seg-0", "seg-1", "seg-2", "seg-3"]
    finally:
        db.close()


def test_rebuild_with_fresh_embedding_replaces_rows(rag_env):
    """文本未变时重建：text_hash 一致，旧向量行不重复堆积。"""
    video_id = seed_video(rag_env, pieces=_ready_video_pieces())
    service = IndexService(rag_env, embedder=FakeEmbedder())
    service.enqueue(rag_env(), video_id)
    service.build_once()
    # 同 attempt 强制重建：先置回 pending
    db = rag_env()
    try:
        row = db.query(RagIndex).filter_by(video_id=video_id).one()
        row.status = "pending"
        db.commit()
    finally:
        db.close()
    assert service.build_once() is True
    db = rag_env()
    try:
        assert db.query(ChunkEmbedding).count() == db.query(RagChunk).count()
    finally:
        db.close()
