"""返回给前端的数据形状。不包含文件路径和密钥。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool


class VideoOut(BaseModel):
    id: str
    title: str
    status: Literal["queued", "transcribing", "indexing", "ready", "failed"]
    processing_mode: Literal["audio_only"]
    duration_sec: float
    size_bytes: int
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    elapsed_sec: float
    attempt: int
    error: ErrorInfo | None


class VideoListOut(BaseModel):
    items: list[VideoOut]
    total: int
    limit: int
    offset: int


class TranscriptSegmentOut(BaseModel):
    id: str
    start_sec: float
    end_sec: float
    text: str


class TranscriptOut(BaseModel):
    video_id: str
    segments: list[TranscriptSegmentOut]


class ChapterOut(BaseModel):
    id: str
    start_sec: float
    end_sec: float
    title: str
    text: str
    segment_ids: list[str]


class SummaryOut(BaseModel):
    video_id: str
    mode: Literal["extractive"]
    chapters: list[ChapterOut]


class CitationOut(BaseModel):
    segment_id: str
    start_sec: float
    end_sec: float
    text: str


class QuestionResultOut(BaseModel):
    id: str
    video_id: str
    question: str
    answer_status: Literal["answered", "not_found", "degraded"]
    mode: Literal["generative", "extractive"]
    answer: str
    citations: list[CitationOut]
    created_at: str
    latency_ms: int
    retrieval_mode: str | None = None
    retrieval_version: str | None = None


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)


class QuestionHistoryOut(BaseModel):
    items: list[QuestionResultOut]
    total: int
    limit: int
    offset: int


class ProgressOut(BaseModel):
    video_id: str
    attempt: int
    position_sec: float
    furthest_sec: float
    version: int
    updated_at: str
    saved: bool


class ProgressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    position_sec: float
    expected_version: int = Field(ge=0)


class ReviewRecordOut(BaseModel):
    id: str
    video_id: str
    video_title: str
    chapter_id: str
    attempt: int
    start_sec: float
    end_sec: float
    text: str
    reviewed: bool
    saved: bool
    resolved: bool
    note: str
    version: int
    is_stale: bool
    updated_at: str


class ReviewListOut(BaseModel):
    items: list[ReviewRecordOut]
    total: int
    limit: int
    offset: int


class ChapterReviewIn(BaseModel):
    """章节标记的部分更新。至少给一个 changed 字段，未提供的字段保持原值。"""

    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    expected_version: int = Field(ge=0)
    reviewed: bool | None = None
    saved: bool | None = None
    resolved: bool | None = None
    note: str | None = Field(default=None, max_length=2000)

    def changed_fields(self) -> dict[str, object]:
        return {name: value for name, value in self.model_dump(exclude={"attempt", "expected_version"}).items() if value is not None}


class ReviewEditIn(BaseModel):
    """待复习清单里的记录编辑。不再需要 attempt：记录本身带着快照批次。"""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    reviewed: bool | None = None
    saved: bool | None = None
    resolved: bool | None = None
    note: str | None = Field(default=None, max_length=2000)

    def changed_fields(self) -> dict[str, object]:
        return {name: value for name, value in self.model_dump(exclude={"expected_version"}).items() if value is not None}


class AssistantMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[AssistantMessageIn] = Field(min_length=1, max_length=20)


class AssistantChatOut(BaseModel):
    answer: str
    mode: Literal["generative", "guide"]


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    display_name: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class HealthOut(BaseModel):
    status: Literal["ok", "not_ready"]
    version: str
    database: str
    transcriber: str
    llm_configured: bool
    transcriber_model: str = "unknown"
    queue_pending: int = 0
    rag_status: str = "disabled"
    rag_indexes_ready: int = 0
    rag_indexes_failed: int = 0
