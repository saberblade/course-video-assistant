"""视频上传、查询、播放、重试、删除和当前视频问答。"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import media
from app.clock import safe_title, utc_now
from app.database import get_db
from app.errors import AppError
from app.models import UNFINISHED_STATUSES, Chapter, Question, Segment, Video
from app.present import chapter_out, segment_out, video_out
from app import qa
from app.schemas import QuestionIn, QuestionResultOut, SummaryOut, TranscriptOut, VideoListOut
from app.storage import save_upload

router = APIRouter(prefix="/api")


def parse_video_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise AppError(422, "INVALID_PARAMETER", "视频编号格式不正确", False) from exc


def get_video(db: Session, video_id: str) -> Video:
    video = db.get(Video, parse_video_id(video_id))
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "视频不存在或已删除", False)
    return video


def unfinished_count(db: Session) -> int:
    count = db.scalar(select(func.count()).select_from(Video).where(Video.status.in_(UNFINISHED_STATUSES)))
    return int(count or 0)


def ensure_ready(video: Video) -> None:
    if video.status == "ready":
        return
    if video.status == "failed":
        raise AppError(409, "VIDEO_NOT_READY", "视频处理失败，请重试或更换文件", False)
    raise AppError(409, "VIDEO_NOT_READY", "视频尚未处理完成，请稍后再试", True)


def queue_full() -> AppError:
    return AppError(429, "QUEUE_FULL", "处理队列已满，请等待已有任务完成", True, {"Retry-After": "10"})


def range_error(size: int) -> AppError:
    return AppError(
        416,
        "RANGE_NOT_SATISFIABLE",
        "请求的媒体字节范围无效",
        False,
        {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
    )


@router.post("/videos", status_code=202)
def upload_video(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    settings = request.app.state.settings
    if unfinished_count(db) >= settings.max_unfinished_jobs:
        raise queue_full()
    db.rollback()

    video_id = str(uuid4())
    temp_path = settings.data_dir / "tmp" / f"{video_id}.upload"
    final_dir = settings.data_dir / "videos" / video_id
    final_path = final_dir / "video.mp4"
    committed = False
    try:
        size = save_upload(file, temp_path, settings.max_upload_bytes)
        if size <= 0:
            raise AppError(422, "INVALID_VIDEO", "文件是空的，无法处理", False)
        info = media.probe_media(temp_path, settings.ffprobe_bin, settings.max_video_seconds)
        with request.app.state.queue_lock:
            db.rollback()
            if unfinished_count(db) >= settings.max_unfinished_jobs:
                raise queue_full()
            final_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(temp_path, final_path)
            now = utc_now()
            video = Video(
                id=video_id,
                title=safe_title(file.filename),
                status="queued",
                processing_mode="audio_only",
                duration_sec=info.duration_sec,
                size_bytes=size,
                created_at=now,
                updated_at=now,
                started_at=None,
                finished_at=None,
                attempt=1,
                error_code=None,
                error_message=None,
                error_retryable=None,
                local_path=str(final_path),
            )
            db.add(video)
            db.commit()
            committed = True
            db.refresh(video)
        body = video_out(video).model_dump()
        return JSONResponse(status_code=202, content=body, headers={"Location": f"/api/videos/{video.id}"})
    finally:
        file.file.close()
        if not committed:
            temp_path.unlink(missing_ok=True)
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)


@router.get("/videos")
def list_videos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> VideoListOut:
    total = int(db.scalar(select(func.count()).select_from(Video)) or 0)
    rows = db.scalars(
        select(Video).order_by(Video.created_at.desc(), Video.id.desc()).limit(limit).offset(offset)
    ).all()
    return VideoListOut(items=[video_out(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/videos/{video_id}")
def read_video(video_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=video_out(get_video(db, video_id)).model_dump())


@router.get("/videos/{video_id}/content")
def read_content(video_id: str, request: Request, db: Session = Depends(get_db)):
    video = get_video(db, video_id)
    path = Path(video.local_path)
    if not path.is_file():
        raise AppError(409, "SOURCE_MISSING", "原视频文件丢失", False)
    size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes", "Content-Type": "video/mp4", "Content-Length": str(size)}
    range_header = request.headers.get("range")
    if size == 0 or not range_header or "," in range_header:
        return StreamingResponse(_iter_file(path, 0, max(size - 1, 0)), media_type="video/mp4", headers=headers)
    start, end = _parse_range(range_header, size)
    part_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(_iter_file(path, start, end), status_code=206, media_type="video/mp4", headers=part_headers)


@router.get("/videos/{video_id}/transcript")
def read_transcript(video_id: str, db: Session = Depends(get_db)) -> TranscriptOut:
    video = get_video(db, video_id)
    ensure_ready(video)
    rows = db.scalars(
        select(Segment).where(Segment.video_id == video.id).order_by(Segment.start_sec, Segment.id)
    ).all()
    if not rows:
        raise AppError(409, "VIDEO_NOT_READY", "视频尚未处理完成，请稍后再试", True)
    return TranscriptOut(video_id=video.id, segments=[segment_out(row) for row in rows])


@router.get("/videos/{video_id}/summary")
def read_summary(video_id: str, db: Session = Depends(get_db)) -> SummaryOut:
    video = get_video(db, video_id)
    ensure_ready(video)
    rows = db.scalars(select(Chapter).where(Chapter.video_id == video.id).order_by(Chapter.start_sec, Chapter.id)).all()
    if not rows:
        raise AppError(409, "VIDEO_NOT_READY", "视频尚未处理完成，请稍后再试", True)
    return SummaryOut(video_id=video.id, mode="extractive", chapters=[chapter_out(row) for row in rows])


@router.post("/videos/{video_id}/questions")
def ask_question(video_id: str, body: QuestionIn, request: Request, db: Session = Depends(get_db)) -> QuestionResultOut:
    question = body.question.strip()
    if not question or len(question) > 300:
        raise AppError(422, "INVALID_QUESTION", "请输入1至300个字符的问题", False)
    video = get_video(db, video_id)
    ensure_ready(video)
    if not qa.try_begin_question(video.id):
        raise AppError(429, "QUESTION_BUSY", "正在回答上一个问题，请稍后再试", True, {"Retry-After": "3"})
    started = time.perf_counter()
    try:
        segments = db.scalars(select(Segment).where(Segment.video_id == video.id)).all()
        draft = qa.draft_answer(list(segments), question, video.duration_sec, request.app.state.settings)
        latency_ms = int((time.perf_counter() - started) * 1000)
        record = Question(
            id=str(uuid4()),
            video_id=video.id,
            question=question,
            answer_status=draft.answer_status,
            mode=draft.mode,
            answer=draft.answer,
            citations_json=json.dumps([item.model_dump() for item in draft.citations], ensure_ascii=False),
            created_at=utc_now(),
            latency_ms=latency_ms,
        )
        db.add(record)
        db.commit()
    finally:
        qa.end_question()
    return QuestionResultOut(
        id=record.id,
        video_id=video.id,
        question=question,
        answer_status=draft.answer_status,  # type: ignore[arg-type]
        mode=draft.mode,  # type: ignore[arg-type]
        answer=draft.answer,
        citations=draft.citations,
        created_at=record.created_at,
        latency_ms=latency_ms,
    )


@router.post("/videos/{video_id}/retry", status_code=202)
def retry_video(video_id: str, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    settings = request.app.state.settings
    video = get_video(db, video_id)
    _ensure_retryable(video)
    with request.app.state.queue_lock:
        db.refresh(video)
        _ensure_retryable(video)
        if unfinished_count(db) >= settings.max_unfinished_jobs:
            raise queue_full()
        db.execute(delete(Segment).where(Segment.video_id == video.id))
        db.execute(delete(Chapter).where(Chapter.video_id == video.id))
        db.execute(delete(Question).where(Question.video_id == video.id))
        video.status = "queued"
        video.attempt += 1
        video.updated_at = utc_now()
        video.started_at = None
        video.finished_at = None
        video.error_code = None
        video.error_message = None
        video.error_retryable = None
        db.commit()
        db.refresh(video)
    return JSONResponse(status_code=202, content=video_out(video).model_dump())


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    settings = request.app.state.settings
    video = get_video(db, video_id)
    if qa.question_in_progress(video.id) or video.status not in ("ready", "failed"):
        raise AppError(409, "VIDEO_BUSY", "视频正在处理或回答问题，暂时不能删除", True)
    source = Path(video.local_path).parent
    trash = settings.data_dir / "trash" / video.id
    moved = False
    if source.exists():
        trash.parent.mkdir(parents=True, exist_ok=True)
        if trash.exists():
            shutil.rmtree(trash)
        shutil.move(str(source), str(trash))
        moved = True
    try:
        db.execute(delete(Segment).where(Segment.video_id == video.id))
        db.execute(delete(Chapter).where(Chapter.video_id == video.id))
        db.execute(delete(Question).where(Question.video_id == video.id))
        db.delete(video)
        db.commit()
    except Exception as exc:
        db.rollback()
        if moved and trash.exists() and not source.exists():
            shutil.move(str(trash), str(source))
        raise AppError(500, "DELETE_FAILED", "删除没有完成，请把请求编号交给系统工程师", True) from exc
    shutil.rmtree(trash, ignore_errors=True)
    return Response(status_code=204)


def _ensure_retryable(video: Video) -> None:
    if video.status != "failed" or not video.error_retryable:
        raise AppError(409, "RETRY_NOT_ALLOWED", "当前状态不能重新处理，请更换文件", False)
    if not Path(video.local_path).is_file():
        raise AppError(409, "SOURCE_MISSING", "原视频文件丢失，不能重试", False)


def _parse_range(header: str, size: int) -> tuple[int, int]:
    value = header.strip()
    if not value.lower().startswith("bytes="):
        raise range_error(size)
    spec = value[6:].strip()
    if spec.startswith("-"):
        try:
            suffix = int(spec[1:])
        except ValueError as exc:
            raise range_error(size) from exc
        if suffix <= 0:
            raise range_error(size)
        if suffix >= size:
            return 0, size - 1
        return size - suffix, size - 1
    if "-" not in spec:
        raise range_error(size)
    start_text, end_text = spec.split("-", 1)
    try:
        start = int(start_text)
    except ValueError as exc:
        raise range_error(size) from exc
    if start < 0 or start >= size:
        raise range_error(size)
    if end_text == "":
        return start, size - 1
    try:
        end = int(end_text)
    except ValueError as exc:
        raise range_error(size) from exc
    if end < start:
        raise range_error(size)
    return start, min(end, size - 1)


def _iter_file(path: Path, start: int, end: int):
    if end < start:
        return
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
