"""RAG 索引生命周期（SYS-02）。

状态机（持久在 rag_indexes 表，服务重启可恢复）：
    pending → building → ready
                 └──────→ failed（last_error 受控记录，不含密钥）

规则（契约 03/02）：
- 课程内容 ready 与向量索引 ready 分开；向量失败不影响基础复习链路。
- 重建同一视频时，旧块/旧向量/旧索引行全部作废（重试或更新不读旧索引）。
- 构建期间不持有长事务：重活（读段、分块、embedding 调用）在事务外，落库用短事务。
- 删除视频由外键级联清理块与向量；本模块另提供显式清理函数。

测试约定：RAG_INDEXING_ENABLED=0 时执行器不启动索引线程；单测注入假 embedder。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.clock import utc_now
from app.models import Segment, Video
from modules.retriever.chunking import CHUNKING_VERSION, build_chunks, segment_ids_json
from modules.retriever.embedding import BailianEmbeddingClient, EmbeddingClient, EmbeddingError, load_embedding_config
from modules.retriever.tables import EMBEDDING_DTYPE, ChunkEmbedding, RagChunk, RagIndex
from modules.retriever.vectorstore import pack_vector

logger = logging.getLogger("course_review.rag")

INDEX_VERSION = "idx_v1"
THREAD_NAME = "rag-indexer"


class IndexService:
    """索引任务的后台构建器。生命周期随执行器（或测试显式 start）。"""

    def __init__(self, session_factory, embedder: EmbeddingClient | None = None) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._idle_wait = float(os.getenv("RAG_INDEX_IDLE_SECONDS", "1.0"))
        self._budget = float(os.getenv("RAG_INDEX_BUDGET_SECONDS", "300"))

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._ensure_tables()
        self._thread = threading.Thread(target=self._run, name=THREAD_NAME, daemon=True)
        self._thread.start()
        logger.info("rag indexer started")

    def _ensure_tables(self) -> None:
        """建表兜底：lifespan 的 create_all 先于本模块导入，这里幂等补建。"""
        try:
            bind = getattr(self._session_factory, "kw", {}).get("bind")
            if bind is None:
                return
            from app.database import Base

            import modules.retriever.tables  # noqa: F401  确保表模型注册进 metadata

            Base.metadata.create_all(bind)
        except Exception as exc:  # noqa: BLE001  建表失败会在首次认领时显式报错
            logger.warning("rag tables ensure failed: %s: %s", exc.__class__.__name__, exc)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("rag indexer stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        db = self._session_factory()
        try:
            recovered = self.recover(db)
            if recovered:
                logger.info("rag index recovery reset %d stale building rows", recovered)
        finally:
            db.close()
        while not self._stop.is_set():
            built = self.build_once()
            if not built:
                self._stop.wait(self._idle_wait)

    # ---------- 登记 ----------
    def enqueue(self, db: Session, video_id: str) -> str | None:
        """视频转写完成后登记 pending。attempt 以 videos 表当前值为准。"""
        video = db.get(Video, video_id)
        if video is None:
            return None
        attempt = int(video.attempt or 1)
        row = db.scalars(
            select(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt == attempt)
        ).first()
        now = utc_now()
        if row is None:
            row = RagIndex(
                id=str(uuid4()),
                video_id=video_id,
                attempt=attempt,
                index_version=INDEX_VERSION,
                model=load_embedding_config().model,
                dimension=load_embedding_config().dimension,
                chunking_version=CHUNKING_VERSION,
                status="pending",
                chunk_count=0,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        elif row.status == "failed":
            row.status = "pending"
            row.last_error = None
            row.updated_at = now
        db.commit()
        return row.id

    def recover(self, db: Session) -> int:
        """服务重启：building 是被打断的中间态，一律重置为 pending 重建。"""
        rows = db.scalars(select(RagIndex).where(RagIndex.status == "building")).all()
        now = utc_now()
        for row in rows:
            row.status = "pending"
            row.updated_at = now
        if rows:
            db.commit()
        return len(rows)

    # ---------- 构建 ----------
    def build_once(self) -> bool:
        """认领一个 pending 并构建。没有可做的任务返回 False。"""
        video_id = self._claim()
        if video_id is None:
            return False
        try:
            self.build(video_id)
        except Exception as exc:  # noqa: BLE001 索引失败必须落 failed 终态，不影响视频本体
            self._fail_row(video_id, "INDEX_BUILD_FAILED", f"{exc.__class__.__name__}: {exc}")
        return True

    def _claim(self) -> str | None:
        db = self._session_factory()
        try:
            row = db.scalars(
                select(RagIndex)
                .where(RagIndex.status == "pending")
                .order_by(RagIndex.updated_at, RagIndex.id)
                .limit(1)
            ).first()
            if row is None:
                return None
            row.status = "building"
            row.updated_at = utc_now()
            db.commit()
            return row.video_id
        except Exception:  # noqa: BLE001
            db.rollback()
            raise
        finally:
            db.close()

    def build(self, video_id: str) -> bool:
        """单个视频的完整构建：读段→分块→embedding→短事务落库。"""
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            if video is None:
                logger.warning("rag index build skip: video %s missing", video_id)
                return False
            attempt = int(video.attempt or 1)
            segments = db.scalars(
                select(Segment).where(Segment.video_id == video_id).order_by(Segment.start_sec, Segment.id)
            ).all()
        finally:
            db.close()

        chunks = build_chunks(list(segments))
        embeddings: list[bytes] | None = None
        embed_seconds = 0.0
        config = load_embedding_config()
        record_dimension = config.dimension
        if chunks:
            embedder = self._embedder
            if embedder is None:
                if not config.configured:
                    self._fail_row(video_id, "EMBED_NOT_CONFIGURED", "向量接口未配置（RAG_EMBEDDING_* / LLM_API_KEY）")
                    return False
                embedder = BailianEmbeddingClient(config)
            began = time.perf_counter()
            vectors = embedder.embed([chunk.text for chunk in chunks], budget_seconds=self._budget)
            embed_seconds = time.perf_counter() - began
            embeddings = [pack_vector(vector) for vector in vectors]
            # 落库维度以实际返回为准（注入的测试客户端维度可与配置不同）
            record_dimension = len(vectors[0]) if vectors else config.dimension
        now = utc_now()
        db = self._session_factory()
        try:
            # 旧索引整体作废：该视频所有块（级联向量）与非当前 attempt 的索引行
            db.execute(delete(RagChunk).where(RagChunk.video_id == video_id))
            db.execute(
                delete(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt != attempt)
            )
            row = db.scalars(
                select(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt == attempt)
            ).first()
            if row is None:
                row = RagIndex(
                    id=str(uuid4()),
                    video_id=video_id,
                    attempt=attempt,
                    index_version=INDEX_VERSION,
                    model=config.model,
                    dimension=config.dimension,
                    chunking_version=CHUNKING_VERSION,
                    status="building",
                    chunk_count=0,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            for chunk, blob in zip(chunks, embeddings or []):
                chunk_row = RagChunk(
                    id=str(uuid4()),
                    video_id=video_id,
                    attempt=attempt,
                    ordinal=chunk.ordinal,
                    segment_ids_json=segment_ids_json(chunk),
                    start_sec=chunk.start_sec,
                    end_sec=chunk.end_sec,
                    text=chunk.text,
                    text_hash=chunk.text_hash,
                    chunking_version=CHUNKING_VERSION,
                )
                db.add(chunk_row)
                db.flush()
                db.add(
                    ChunkEmbedding(
                        chunk_id=chunk_row.id,
                        model=config.model,
                        dimension=record_dimension,
                        vector_blob=blob,
                        dtype=EMBEDDING_DTYPE,
                        text_hash=chunk.text_hash,
                        status="ready",
                        updated_at=now,
                    )
                )
            row.status = "ready"
            row.last_error = None
            row.chunk_count = len(chunks)
            row.model = config.model
            row.dimension = record_dimension
            row.chunking_version = CHUNKING_VERSION
            row.updated_at = now
            db.commit()
            logger.info(
                "rag index ready video_id=%s chunks=%d embed=%.2fs", video_id, len(chunks), embed_seconds
            )
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _fail_row(self, video_id: str, code: str, message: str) -> None:
        db = self._session_factory()
        try:
            video = db.get(Video, video_id)
            attempt = int(video.attempt or 1) if video is not None else 1
            row = db.scalars(
                select(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt == attempt)
            ).first()
            if row is not None:
                row.status = "failed"
                row.last_error = f"{code}: {message}"[:290]
                row.updated_at = utc_now()
                db.commit()
                logger.warning("rag index failed video_id=%s code=%s", video_id, code)
        finally:
            db.close()

    # ---------- 查询/清理 ----------
    @staticmethod
    def get_status(db: Session, video_id: str) -> dict:
        """GET /api/videos/{id}/retrieval-status 的数据来源（许梓轩挂路由）。"""
        video = db.get(Video, video_id)
        if video is None:
            return {}
        attempt = int(video.attempt or 1)
        row = db.scalars(
            select(RagIndex).where(RagIndex.video_id == video_id, RagIndex.attempt == attempt)
        ).first()
        chunk_count = 0
        if row is not None:
            chunk_rows = db.scalars(
                select(RagChunk).where(RagChunk.video_id == video_id, RagChunk.attempt == attempt)
            ).all()
            chunk_count = len(chunk_rows)
        config = load_embedding_config()
        return {
            "video_id": video_id,
            "attempt": attempt,
            "index_status": row.status if row is not None else "absent",
            "index_version": row.index_version if row is not None else None,
            "model": row.model if row is not None else None,
            "dimension": row.dimension if row is not None else None,
            "chunking_version": row.chunking_version if row is not None else None,
            "chunk_count": chunk_count,
            "last_error": row.last_error if row is not None else None,
            "updated_at": row.updated_at if row is not None else None,
            "embedding_configured": config.configured,
        }

    @staticmethod
    def cleanup_video(db: Session, video_id: str) -> None:
        """显式清理（删除路由可调；外键级联本来也会清）。"""
        db.execute(delete(RagChunk).where(RagChunk.video_id == video_id))
        db.execute(delete(RagIndex).where(RagIndex.video_id == video_id))
        db.commit()


def rag_indexing_enabled() -> bool:
    return os.getenv("RAG_INDEXING_ENABLED", "0") != "0"
