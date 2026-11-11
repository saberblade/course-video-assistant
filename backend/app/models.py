"""四本账：视频、转写句子、章节、问答。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

UNFINISHED_STATUSES = ("queued", "transcribing", "indexing")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
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
    created_at: Mapped[str] = mapped_column(String(40))
    latency_ms: Mapped[int] = mapped_column(Integer)
