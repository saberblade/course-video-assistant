"""健康检查。不调用通义千问，也不假装转写模型或索引线程已经就绪。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, Settings
from app.models import UNFINISHED_STATUSES, Video
from app.schemas import HealthOut

router = APIRouter(prefix="/api")

WHISPER_MODEL_DIR = "models/faster-whisper-small"
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")


def transcriber_state() -> str:
    module_file = PROJECT_ROOT / "modules" / "transcriber" / "__init__.py"
    if module_file.is_file():
        return "ready"
    return "missing"


def transcriber_model_state() -> str:
    """模型文件是否真的在盘上。缺失时转写会在任务里失败，不能报健康。"""
    configured = os.getenv("WHISPER_MODEL_DIR", WHISPER_MODEL_DIR)
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if all((path / name).is_file() for name in MODEL_FILES):
        return "ready"
    return "missing"


def queue_state(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Video).where(Video.status.in_(UNFINISHED_STATUSES))) or 0)


def rag_state(request: Request) -> tuple[str, int, int]:
    """索引线程是否在跑，以及 ready/failed 登记数。只读真实状态，不按配置猜测。"""
    from modules.retriever.tables import RagIndex

    db = request.app.state.session_factory()
    try:
        ready = int(db.scalar(select(func.count()).select_from(RagIndex).where(RagIndex.status == "ready")) or 0)
        failed = int(db.scalar(select(func.count()).select_from(RagIndex).where(RagIndex.status == "failed")) or 0)
    except Exception:
        return ("unavailable", 0, 0)
    finally:
        db.close()

    executor = getattr(request.app.state, "task_executor", None)
    indexer = getattr(executor, "_rag", None) if executor is not None else None
    running = bool(indexer is not None and indexer.is_running())
    if running:
        return ("ready", ready, failed)
    return ("disabled", ready, failed)


def read_health(db: Session, settings: Settings, request: Request | None = None) -> tuple[int, HealthOut]:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    transcriber = transcriber_state()
    model = transcriber_model_state()
    pending = queue_state(db) if database == "ok" else 0
    rag, rag_ready, rag_failed = rag_state(request) if request is not None else ("disabled", 0, 0)

    ready = database == "ok" and transcriber == "ready"
    body = HealthOut(
        status="ok" if ready else "not_ready",
        version=settings.app_version,
        database=database,
        transcriber=transcriber,
        llm_configured=settings.llm_configured,
        transcriber_model=model,
        queue_pending=pending,
        rag_status=rag,
        rag_indexes_ready=rag_ready,
        rag_indexes_failed=rag_failed,
    )
    return (200 if ready else 503), body


@router.get("/health")
def health(request: Request) -> JSONResponse:
    db = request.app.state.session_factory()
    try:
        status_code, body = read_health(db, request.app.state.settings, request)
    finally:
        db.close()
    return JSONResponse(status_code=status_code, content=body.model_dump())
