"""学习档案：播放位置、章节标记与备注、待复习清单。

并发规则（契约 02）：进度和标记都用带 version 条件的原子 UPDATE，
以受影响行数判断成功，不做“先查版本再无条件写入”。
"""

from __future__ import annotations

import math
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_csrf, require_user
from app.clock import utc_now
from app.database import get_db
from app.errors import AppError
from app.models import Chapter, PlaybackProgress, ReviewRecord, Video
from app.routers.videos import current_video
from app.schemas import (
    ChapterReviewIn,
    ProgressIn,
    ProgressOut,
    ReviewEditIn,
    ReviewListOut,
    ReviewRecordOut,
)

router = APIRouter(prefix="/api", tags=["profile"])

NOTE_LIMIT = 2000


def _progress_out(row: PlaybackProgress) -> ProgressOut:
    return ProgressOut(
        video_id=row.video_id,
        attempt=row.attempt,
        position_sec=row.position_sec,
        furthest_sec=row.furthest_sec,
        version=row.version,
        updated_at=row.updated_at,
        saved=True,
    )


def _record_out(row: ReviewRecord, current_attempt: int, video_title: str) -> ReviewRecordOut:
    return ReviewRecordOut(
        id=row.id,
        video_id=row.video_id,
        video_title=video_title,
        chapter_id=row.chapter_id_snapshot,
        attempt=row.source_attempt,
        start_sec=row.start_sec,
        end_sec=row.end_sec,
        text=row.text_snapshot,
        reviewed=bool(row.reviewed),
        saved=bool(row.saved),
        resolved=bool(row.resolved),
        note=row.note or "",
        version=row.version,
        is_stale=row.source_attempt != current_attempt,
        updated_at=row.updated_at,
    )


@router.get("/videos/{video_id}/progress", response_model=ProgressOut)
def read_progress(video_id: str, request: Request, db: Session = Depends(get_db)) -> ProgressOut:
    video = current_video(request, db, video_id)
    user = request.state.current_user
    row = db.scalars(
        select(PlaybackProgress).where(
            PlaybackProgress.user_id == user.id,
            PlaybackProgress.video_id == video.id,
            PlaybackProgress.attempt == video.attempt,
        )
    ).first()
    if row is None:
        return ProgressOut(
            video_id=video.id,
            attempt=video.attempt,
            position_sec=0.0,
            furthest_sec=0.0,
            version=0,
            updated_at="",
            saved=False,
        )
    return _progress_out(row)


@router.put("/videos/{video_id}/progress", response_model=ProgressOut)
def save_progress(
    video_id: str,
    body: ProgressIn,
    request: Request,
    db: Session = Depends(get_db),
) -> ProgressOut:
    video = current_video(request, db, video_id)
    require_csrf(request)
    user = request.state.current_user

    if body.attempt != video.attempt:
        raise AppError(409, "STALE_ATTEMPT", "视频已重新处理，请刷新后从头继续", False)
    if not math.isfinite(body.position_sec):
        raise AppError(422, "INVALID_PARAMETER", "播放位置不是有效数值", False)
    duration = float(video.duration_sec or 0)
    if body.position_sec < 0 or body.position_sec > duration:
        raise AppError(422, "INVALID_PARAMETER", "播放位置超出视频时长", False)

    now = utc_now()
    position = round(float(body.position_sec), 3)

    if body.expected_version == 0:
        row = PlaybackProgress(
            id=str(uuid4()),
            user_id=user.id,
            video_id=video.id,
            attempt=video.attempt,
            position_sec=position,
            furthest_sec=position,
            version=1,
            updated_at=now,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # 并发下的首次创建：另一请求已经建好，按版本冲突让客户端重新读取。
            raise AppError(409, "VERSION_CONFLICT", "这个视频已在另一个窗口保存过进度，请先刷新", False) from None
        db.refresh(row)
        return _progress_out(row)

    # 一次 UPDATE 同时完成版本校验与最远位置取大，避免读改写竞态。
    changed = db.execute(
        update(PlaybackProgress)
        .where(
            PlaybackProgress.user_id == user.id,
            PlaybackProgress.video_id == video.id,
            PlaybackProgress.attempt == video.attempt,
            PlaybackProgress.version == body.expected_version,
        )
        .values(
            position_sec=position,
            furthest_sec=func.max(PlaybackProgress.furthest_sec, position),
            version=PlaybackProgress.version + 1,
            updated_at=now,
        )
    ).rowcount
    if not changed:
        db.rollback()
        exists = db.scalars(
            select(PlaybackProgress).where(
                PlaybackProgress.user_id == user.id,
                PlaybackProgress.video_id == video.id,
                PlaybackProgress.attempt == video.attempt,
            )
        ).first()
        if exists is None:
            raise AppError(409, "VERSION_CONFLICT", "进度记录已不存在，请重新读取后再保存", False)
        raise AppError(
            409,
            "VERSION_CONFLICT",
            "进度已在另一个窗口更新，请先刷新再继续",
            False,
        )
    db.commit()
    row = db.scalars(
        select(PlaybackProgress).where(
            PlaybackProgress.user_id == user.id,
            PlaybackProgress.video_id == video.id,
            PlaybackProgress.attempt == video.attempt,
        )
    ).first()
    if row is None:  # pragma: no cover - 刚更新成功不会缺失
        raise AppError(500, "PROGRESS_MISSING", "进度保存后无法读取，请重试", True)
    return _progress_out(row)


@router.get("/videos/{video_id}/review-records", response_model=ReviewListOut)
def list_video_records(
    video_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewListOut:
    video = current_video(request, db, video_id)
    user = request.state.current_user
    base = (
        ReviewRecord.user_id == user.id,
        ReviewRecord.video_id == video.id,
        ReviewRecord.source_attempt == video.attempt,
    )
    total = int(db.scalar(select(func.count()).select_from(ReviewRecord).where(*base)) or 0)
    rows = db.scalars(
        select(ReviewRecord)
        .where(*base)
        .order_by(ReviewRecord.start_sec, ReviewRecord.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ReviewListOut(
        items=[_record_out(row, video.attempt, video.title) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/videos/{video_id}/chapters/{chapter_id}/review", response_model=ReviewRecordOut)
def upsert_chapter_review(
    video_id: str,
    chapter_id: str,
    body: ChapterReviewIn,
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewRecordOut:
    video = current_video(request, db, video_id)
    require_csrf(request)
    user = request.state.current_user

    changed = body.changed_fields()
    if not changed:
        raise AppError(422, "INVALID_PARAMETER", "至少要修改标记或备注中的一项", False)
    if body.attempt != video.attempt:
        raise AppError(409, "STALE_ATTEMPT", "视频已重新处理，请刷新后再标记", False)
    if "note" in changed and len(str(changed["note"])) > NOTE_LIMIT:
        raise AppError(422, "INVALID_PARAMETER", f"备注不能超过 {NOTE_LIMIT} 个字符", False)

    chapter = db.get(Chapter, chapter_id)
    if chapter is None or chapter.video_id != video.id:
        raise AppError(404, "CHAPTER_NOT_FOUND", "章节不存在或已随重新处理失效", False)

    key = (
        ReviewRecord.user_id == user.id,
        ReviewRecord.video_id == video.id,
        ReviewRecord.source_attempt == video.attempt,
        ReviewRecord.chapter_id_snapshot == chapter.id,
    )
    now = utc_now()

    if body.expected_version == 0:
        row = ReviewRecord(
            id=str(uuid4()),
            user_id=user.id,
            video_id=video.id,
            source_attempt=video.attempt,
            chapter_id_snapshot=chapter.id,
            start_sec=chapter.start_sec,
            end_sec=chapter.end_sec,
            text_snapshot=chapter.text,
            reviewed=int(bool(changed.get("reviewed", False))),
            saved=int(bool(changed.get("saved", False))),
            resolved=int(bool(changed.get("resolved", False))),
            note=str(changed.get("note", "")),
            version=1,
            updated_at=now,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise AppError(409, "VERSION_CONFLICT", "这个章节已在另一个窗口保存过，请先刷新", False) from None
        db.refresh(row)
        return _record_out(row, video.attempt, video.title)

    values: dict[str, object] = {"version": ReviewRecord.version + 1, "updated_at": now}
    if "reviewed" in changed:
        values["reviewed"] = int(bool(changed["reviewed"]))
    if "saved" in changed:
        values["saved"] = int(bool(changed["saved"]))
    if "resolved" in changed:
        values["resolved"] = int(bool(changed["resolved"]))
    if "note" in changed:
        values["note"] = str(changed["note"])

    affected = db.execute(
        update(ReviewRecord)
        .where(*key, ReviewRecord.version == body.expected_version)
        .values(**values)
    ).rowcount
    if not affected:
        db.rollback()
        raise AppError(409, "VERSION_CONFLICT", "标记已在另一个窗口更新，请先刷新", False)
    db.commit()
    row = db.scalars(select(ReviewRecord).where(*key)).first()
    if row is None:  # pragma: no cover
        raise AppError(500, "RECORD_MISSING", "标记保存后无法读取，请重试", True)
    return _record_out(row, video.attempt, video.title)


@router.get("/me/review-records", response_model=ReviewListOut)
def list_my_records(
    request: Request,
    status: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewListOut:
    user = require_user(request, db)
    mode = status.strip().lower()
    if mode not in ("open", "resolved", "all"):
        raise AppError(422, "INVALID_PARAMETER", "status 只支持 open、resolved、all", False)

    condition = ReviewRecord.user_id == user.id
    if mode == "open":
        condition = condition & (ReviewRecord.saved == 1) & (ReviewRecord.resolved == 0)
    elif mode == "resolved":
        condition = condition & (ReviewRecord.resolved == 1)
    else:
        condition = condition & (
            (ReviewRecord.saved == 1) | (ReviewRecord.resolved == 1) | (ReviewRecord.reviewed == 1)
        )

    total = int(db.scalar(select(func.count()).select_from(ReviewRecord).where(condition)) or 0)
    rows = db.scalars(
        select(ReviewRecord)
        .where(condition)
        .order_by(ReviewRecord.updated_at.desc(), ReviewRecord.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    attempts, titles = _video_meta(db, {row.video_id for row in rows})
    return ReviewListOut(
        items=[
            _record_out(row, attempts.get(row.video_id, row.source_attempt), titles.get(row.video_id, "课程视频"))
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/me/review-records/{record_id}", response_model=ReviewRecordOut)
def edit_my_record(
    record_id: str,
    body: ReviewEditIn,
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewRecordOut:
    user = require_user(request, db)
    require_csrf(request)
    row = db.get(ReviewRecord, record_id)
    if row is None or row.user_id != user.id:
        raise AppError(404, "RECORD_NOT_FOUND", "记录不存在或不属于当前账号", False)

    changed = body.changed_fields()
    if not changed:
        raise AppError(422, "INVALID_PARAMETER", "至少要修改标记或备注中的一项", False)
    if "note" in changed and len(str(changed["note"])) > NOTE_LIMIT:
        raise AppError(422, "INVALID_PARAMETER", f"备注不能超过 {NOTE_LIMIT} 个字符", False)

    values: dict[str, object] = {"version": ReviewRecord.version + 1, "updated_at": utc_now()}
    for name in ("reviewed", "saved", "resolved"):
        if name in changed:
            values[name] = int(bool(changed[name]))
    if "note" in changed:
        values["note"] = str(changed["note"])

    affected = db.execute(
        update(ReviewRecord)
        .where(ReviewRecord.id == record_id, ReviewRecord.version == body.expected_version)
        .values(**values)
    ).rowcount
    if not affected:
        db.rollback()
        # 旧批次的记录被别的窗口改过，或者版本号已经前进。
        raise AppError(409, "VERSION_CONFLICT", "记录已在另一个窗口更新，请先刷新", False)
    db.commit()
    db.refresh(row)
    attempts, titles = _video_meta(db, {row.video_id})
    return _record_out(row, attempts.get(row.video_id, row.source_attempt), titles.get(row.video_id, "课程视频"))


def _video_meta(db: Session, video_ids: set[str]) -> tuple[dict[str, int], dict[str, str]]:
    """一次查出涉及的视频批次与标题，清单页不用逐条回查。"""
    if not video_ids:
        return {}, {}
    rows = db.execute(select(Video.id, Video.attempt, Video.title).where(Video.id.in_(video_ids))).all()
    return {video_id: attempt for video_id, attempt, _title in rows}, {video_id: title for video_id, _attempt, title in rows}
