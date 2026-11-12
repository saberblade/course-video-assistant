"""视频、转写、章节、问答、账号会话与学习档案。"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

UNFINISHED_STATUSES = ("queued", "transcribing", "indexing")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username_normalized: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[str] = mapped_column(String(40))


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), index=True)
    processing_mode: Mapped[str] = mapped_column(String(20), default="audio_only")
    duration_sec: Mapped[float] = mapped_column()
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error_retryable: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_path: Mapped[str] = mapped_column(Text)


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    start_sec: Mapped[float] = mapped_column()
    end_sec: Mapped[float] = mapped_column()
    text: Mapped[str] = mapped_column(Text)


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    start_sec: Mapped[float] = mapped_column()
    end_sec: Mapped[float] = mapped_column()
    title: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    segment_ids_json: Mapped[str] = mapped_column(Text)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(String(300))
    answer_status: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    answer: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    # 契约 02：检索方式与索引版本单独记录，旧记录迁移为 bm25，不伪称 hybrid。
    retrieval_mode: Mapped[str | None] = mapped_column(String(20), nullable=True, default="bm25")
    retrieval_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PlaybackProgress(Base):
    """一个用户在一个视频一个处理批次上的播放位置。version 用于并发校验。"""

    __tablename__ = "playback_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    position_sec: Mapped[float] = mapped_column(Float)
    furthest_sec: Mapped[float] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(40))

    __table_args__ = (UniqueConstraint("user_id", "video_id", "attempt", name="uq_progress_user_video_attempt"),)


class ReviewRecord(Base):
    """章节复习标记与备注。原章节 ID 只是快照标识，重试后旧备注仍然保留。"""

    __tablename__ = "review_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    source_attempt: Mapped[int] = mapped_column(Integer)
    chapter_id_snapshot: Mapped[str] = mapped_column(String(36))
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    text_snapshot: Mapped[str] = mapped_column(Text)
    reviewed: Mapped[int] = mapped_column(Integer, default=0)
    saved: Mapped[int] = mapped_column(Integer, default=0)
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "video_id",
            "source_attempt",
            "chapter_id_snapshot",
            name="uq_review_user_video_attempt_chapter",
        ),
    )
