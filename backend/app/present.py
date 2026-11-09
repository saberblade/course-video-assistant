"""把数据库里的一行，变成接口约定的视频对象。"""

from __future__ import annotations

import json

from app.clock import elapsed_seconds
from app.models import Chapter, Segment, Video
from app.schemas import ChapterOut, ErrorInfo, TranscriptSegmentOut, VideoOut


def video_out(video: Video) -> VideoOut:
    error = None
    if video.error_code and video.error_message is not None and video.error_retryable is not None:
        error = ErrorInfo(
            code=video.error_code,
            message=video.error_message,
            retryable=bool(video.error_retryable),
        )
    return VideoOut(
        id=video.id,
        title=video.title,
        status=video.status,  # type: ignore[arg-type]
        processing_mode="audio_only",
        duration_sec=video.duration_sec,
        size_bytes=video.size_bytes,
        created_at=video.created_at,
        updated_at=video.updated_at,
        started_at=video.started_at,
        finished_at=video.finished_at,
        elapsed_sec=elapsed_seconds(video.status, video.started_at, video.finished_at),
        attempt=video.attempt,
        error=error,
    )


def segment_out(segment: Segment) -> TranscriptSegmentOut:
    return TranscriptSegmentOut(
        id=segment.id,
        start_sec=segment.start_sec,
        end_sec=segment.end_sec,
        text=segment.text,
    )


def chapter_out(chapter: Chapter) -> ChapterOut:
    return ChapterOut(
        id=chapter.id,
        start_sec=chapter.start_sec,
        end_sec=chapter.end_sec,
        title=chapter.title,
        text=chapter.text,
        segment_ids=json.loads(chapter.segment_ids_json),
    )
