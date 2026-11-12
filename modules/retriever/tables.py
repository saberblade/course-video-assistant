"""RAG 表模型（SYS-01/SYS-02）。

字段口径来自 docs/中期到答辩之前的规划/02_接口与数据契约.md：
- rag_indexes：索引任务持久状态（pending/building/ready/failed），重启可恢复。
- rag_chunks：版本化原文块（真实转写片段，不掺模型生成内容）。
- chunk_embeddings：float32 little-endian 向量；只读同模型同维度同文本哈希的有效向量。

三张表都挂 app.database.Base，建表走 Base.metadata.create_all（幂等）。
Alembic 迁移链由李沛丰统一维护；本文件只定义字段，不改迁移。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

INDEX_STATUSES = ("pending", "building", "ready", "failed")
EMBEDDING_DTYPE = "float32_le"


class RagIndex(Base):
    """一个视频一次处理批次（attempt）的向量索引登记。"""

    __tablename__ = "rag_indexes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, index=True)
    index_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[int] = mapped_column(Integer)
    chunking_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), index=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40), index=True)

    __table_args__ = (UniqueConstraint("video_id", "attempt", name="uq_rag_index_video_attempt"),)


class RagChunk(Base):
    """相邻完整转写句合并出的原文块。时间来自真实 segment 区间。"""

    __tablename__ = "rag_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, index=True)
    ordinal: Mapped[int] = mapped_column(Integer)  # 块内时间顺序，用于稳定排序
    segment_ids_json: Mapped[str] = mapped_column(Text)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    chunking_version: Mapped[str] = mapped_column(String(32))


class ChunkEmbedding(Base):
    """块向量。同块同模型同维度同文本哈希唯一；重嵌后旧行删除。"""

    __tablename__ = "chunk_embeddings"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("rag_chunks.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[int] = mapped_column(Integer)
    vector_blob: Mapped[bytes] = mapped_column(LargeBinary)
    dtype: Mapped[str] = mapped_column(String(16), default=EMBEDDING_DTYPE)
    text_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ready")
    updated_at: Mapped[str] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("chunk_id", "model", "dimension", "text_hash", name="uq_chunk_embedding"),
    )
