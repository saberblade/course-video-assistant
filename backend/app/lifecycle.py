"""服务重新启动时，把做到一半的任务标成失败。排队中的保留。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utc_now
from app.models import Video


def recover_interrupted(db: Session) -> None:
    now = utc_now()
    rows = db.scalars(select(Video).where(Video.status.in_(("transcribing", "indexing")))).all()
    for video in rows:
        video.status = "failed"
        video.error_code = "PROCESS_INTERRUPTED"
        video.error_message = "上次处理因服务重启中断，可重试"
        video.error_retryable = 1
        video.finished_at = now
        video.updated_at = now
    if rows:
        db.commit()
