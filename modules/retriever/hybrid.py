"""混合检索（SYS-01/SYS-02）。

两路召回：
- BM25：本模块分块（chunks_v1）上的关键词检索，与基线 A（60 秒窗）分块口径不同，
  评测对照时注意区分（B=新块 BM25，C=BM25+向量 RRF）。
- 语义向量：查询文本实时 embedding，与已落库块向量做余弦排序。

融合用 RRF（k=60，rank 从 1 起），只合并排名、不混合原始分数。
失败受控：向量接口故障/索引未就绪 → bm25_fallback，绝不产生假引用。

返回类型复用 app.retrieval.RetrievalHit，qa.py 既有引用回填逻辑零改动可接。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import time

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Segment, Video
from app.retrieval import DEFAULT_MAX_CHARS, DEFAULT_TOP_K, SYNONYMS, HitSegment, RetrievalHit
from modules.retriever.embedding import (
    BailianEmbeddingClient,
    EmbeddingClient,
    EmbeddingError,
    load_embedding_config,
    normalize,
)
from modules.retriever.service import INDEX_VERSION
from modules.retriever.tables import ChunkEmbedding, RagChunk, RagIndex
from modules.retriever.vectorstore import rank_chunks_by_cosine, rrf_fuse, unpack_vector

logger = logging.getLogger("course_review.rag")

RRF_K = 60
_QUERY_CACHE: dict[tuple[str, int, str], np.ndarray] = {}
_CACHE_LOCK = threading.Lock()


def retrieval_mode_default() -> str:
    mode = os.getenv("RAG_RETRIEVAL_MODE", "bm25").strip().lower()
    return mode if mode in ("bm25", "hybrid") else "bm25"


def retrieve(
    db: Session,
    video_id: str,
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
    embedder: EmbeddingClient | None = None,
    budget_seconds: float = 8.0,
    mode: str | None = None,
) -> "RetrievalOutcome":
    """在当前视频当前 attempt 的有效索引上检索。失败与缺索引都显式降级。"""
    requested = (mode or retrieval_mode_default()).strip().lower()
    diagnostics: dict[str, object] = {"requested_mode": requested}

    video = db.get(Video, video_id)
    if video is None:
        return RetrievalOutcome([], "unavailable", {"reason": "video_not_found"})
    attempt = int(video.attempt or 1)

    row = db.scalars(
        select(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt == attempt)
    ).first()
    chunks = db.scalars(
        select(RagChunk)
        .where(RagChunk.video_id == video_id, RagChunk.attempt == attempt)
        .order_by(RagChunk.ordinal)
    ).all()
    if row is None or row.status != "ready" or not chunks:
        return RetrievalOutcome(
            [],
            "bm25_fallback",
            {**diagnostics, "reason": "index_not_ready", "index_status": row.status if row is not None else "absent"},
        )
    diagnostics.update(
        {
            "index_status": row.status,
            "index_version": row.index_version,
            "model": row.model,
            "dimension": row.dimension,
            "chunking_version": row.chunking_version,
            "chunks": len(chunks),
        }
    )
    if row.index_version != INDEX_VERSION:
        return RetrievalOutcome([], "bm25_fallback", {**diagnostics, "reason": "index_version_mismatch"})

    bm25_ranked = _bm25_rank_chunks(chunks, question)
    diagnostics["bm25_candidates"] = len(bm25_ranked)

    if requested != "hybrid":
        return _assemble(db, chunks, bm25_ranked[:top_k], "bm25", {**diagnostics, "vector_candidates": 0}, top_k, max_chars)

    config = load_embedding_config()
    embedding_rows = _load_embeddings(db, chunks, config.model, config.dimension)
    diagnostics["embedding_rows"] = len(embedding_rows)
    try:
        began = time.perf_counter()
        query_vector, cache_hit = _query_embedding(embedder, question, config, budget_seconds)
        diagnostics["cache_hit"] = cache_hit
        diagnostics["embed_seconds"] = 0.0 if cache_hit else round(time.perf_counter() - began, 4)
        vector_ranked, zero_norm_skipped = rank_chunks_by_cosine(
            query_vector, [(chunk.id, embedding_rows[chunk.id]) for chunk in chunks if chunk.id in embedding_rows]
        )
        diagnostics["vector_candidates"] = len(vector_ranked)
        diagnostics["zero_norm_skipped"] = zero_norm_skipped
        fused = rrf_fuse([bm25_ranked, vector_ranked], k=RRF_K)
        diagnostics["rrf_k"] = RRF_K
        return _assemble(db, chunks, fused[:top_k], "hybrid", diagnostics, top_k, max_chars)
    except EmbeddingError as exc:
        logger.info("hybrid retrieval fell back to bm25: %s", exc.code)
        return _assemble(
            db,
            chunks,
            bm25_ranked[:top_k],
            "bm25_fallback",
            {**diagnostics, "retrieval_error": exc.code},
            top_k,
            max_chars,
        )


def retrieve_with_legacy_fallback(
    db: Session,
    video_id: str,
    question: str,
    segments: list,
    duration_sec: float,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
    embedder: EmbeddingClient | None = None,
    budget_seconds: float = 8.0,
    mode: str | None = None,
) -> "RetrievalOutcome":
    """qa 集成入口：模块无可用结果时回退基线 A（60 秒窗 BM25），许梓轩接这一处即可。"""
    from app.retrieval import search_segments

    outcome = retrieve(
        db,
        video_id,
        question,
        top_k=top_k,
        max_chars=max_chars,
        embedder=embedder,
        budget_seconds=budget_seconds,
        mode=mode,
    )
    if outcome.hits:
        return outcome
    legacy = search_segments(segments, question, duration_sec, top_k=top_k, max_chars=max_chars)
    diagnostics = {**outcome.diagnostics, "legacy_fallback": True}
    return RetrievalOutcome(legacy, "bm25_fallback", diagnostics)


def _assemble(
    db: Session,
    chunks: list[RagChunk],
    ranked_ids: list[str],
    mode_used: str,
    diagnostics: dict,
    top_k: int,
    max_chars: int,
) -> "RetrievalOutcome":
    """把入选块转成 RetrievalHit：按预算收块，引用段从 Segment 表取真实区间。"""
    by_id = {chunk.id: chunk for chunk in chunks}
    chosen = [by_id[cid] for cid in ranked_ids if cid in by_id]

    used = 0
    hits: list[RetrievalHit] = []
    for chunk in chosen:
        if used + len(chunk.text) > max_chars:
            logger.info("retrieval kept %s characters after budget cut", used)
            break
        used += len(chunk.text)
        chunk_segment_ids = json.loads(chunk.segment_ids_json) if chunk.segment_ids_json else []
        segment_rows = (
            db.scalars(select(Segment).where(Segment.id.in_(chunk_segment_ids))).all()
            if chunk_segment_ids
            else []
        )
        by_sid = {segment.id: segment for segment in segment_rows}
        hit_segments = [
            HitSegment(segment.id, segment.start_sec, segment.end_sec, segment.text.strip())
            for segment in sorted(by_sid.values(), key=lambda item: (item.start_sec, item.id))
        ]
        hits.append(
            RetrievalHit(
                start_sec=chunk.start_sec,
                end_sec=chunk.end_sec,
                text=chunk.text,
                segment_ids=chunk_segment_ids,
                segments=hit_segments,
            )
        )
    return RetrievalOutcome(hits, mode_used, diagnostics)


def _bm25_rank_chunks(chunks: list[RagChunk], question: str) -> list[str]:
    """块上的 BM25 排名。小语料用恒正 IDF（与基线实现同口径）。"""
    import jieba
    from rank_bm25 import BM25Okapi

    corpus_tokens = [_tokenize(chunk.text) for chunk in chunks]
    query_tokens = _tokenize(question)
    pairs = [(chunk, tokens) for chunk, tokens in zip(chunks, corpus_tokens) if tokens]
    if not pairs or not query_tokens:
        return []
    model = BM25Okapi([tokens for _chunk, tokens in pairs])
    document_frequency: dict[str, int] = {}
    for frequencies in model.doc_freqs:
        for word in frequencies:
            document_frequency[word] = document_frequency.get(word, 0) + 1
    model.idf = {
        word: math.log((model.corpus_size - freq + 0.5) / (freq + 0.5) + 1)
        for word, freq in document_frequency.items()
    }
    scores = model.get_scores(query_tokens)
    ranked = [
        chunk.id
        for score, (chunk, _tokens) in sorted(
            zip(scores, pairs), key=lambda item: (-item[0], item[1][0].ordinal)
        )
        if score > 0
    ]
    return ranked


def _tokenize(text: str) -> list[str]:
    import jieba

    normalized = re.sub(r"\s+", " ", text.strip().lower())
    for source, target in SYNONYMS.items():
        normalized = normalized.replace(source, target)
    return [token for token in jieba.lcut(normalized) if token.strip()]


def _load_embeddings(
    db: Session, chunks: list[RagChunk], model: str, dimension: int
) -> dict[str, bytes]:
    """只取同模型同维度且文本哈希与块一致的有效向量。"""
    if not chunks:
        return {}
    rows = db.scalars(
        select(ChunkEmbedding).where(
            ChunkEmbedding.chunk_id.in_([chunk.id for chunk in chunks]),
            ChunkEmbedding.model == model,
            ChunkEmbedding.dimension == dimension,
            ChunkEmbedding.status == "ready",
        )
    ).all()
    hashes = {chunk.id: chunk.text_hash for chunk in chunks}
    return {row.chunk_id: row.vector_blob for row in rows if hashes.get(row.chunk_id) == row.text_hash}


def _query_embedding(
    embedder: EmbeddingClient | None,
    question: str,
    config,
    budget_seconds: float,
) -> tuple[np.ndarray, bool]:
    """查询向量化：进程内缓存命中直接返回；未命中调接口并登记。"""
    digest = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()
    key = (config.model, config.dimension, digest)
    with _CACHE_LOCK:
        cached = _QUERY_CACHE.get(key)
    if cached is not None:
        return cached, True
    client = embedder or BailianEmbeddingClient(config)
    vectors = client.embed([question], budget_seconds=budget_seconds)
    if not vectors:
        raise EmbeddingError("EMBED_EMPTY_VECTOR")
    unit = normalize(vectors[0])
    with _CACHE_LOCK:
        _QUERY_CACHE[key] = unit
    return unit, False


class RetrievalOutcome:
    """检索结果：命中块（含真实引用段）、实际使用方式与诊断信息。"""

    __slots__ = ("hits", "mode_used", "diagnostics")

    def __init__(self, hits: list[RetrievalHit], mode_used: str, diagnostics: dict) -> None:
        self.hits = hits
        self.mode_used = mode_used
        self.diagnostics = diagnostics

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return f"RetrievalOutcome(mode={self.mode_used}, hits={len(self.hits)})"
