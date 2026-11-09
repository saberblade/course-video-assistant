"""健康检查。不调用通义千问，也不假装转写模块已经装好。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, Settings
from app.schemas import HealthOut

router = APIRouter(prefix="/api")


def transcriber_state() -> str:
    module_file = PROJECT_ROOT / "modules" / "transcriber" / "__init__.py"
    if module_file.is_file():
        return "ready"
    return "missing"


def read_health(db: Session, settings: Settings) -> tuple[int, HealthOut]:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    transcriber = transcriber_state()
    ready = database == "ok" and transcriber == "ready"
    body = HealthOut(
        status="ok" if ready else "not_ready",
        version=settings.app_version,
        database=database,
        transcriber=transcriber,
        llm_configured=settings.llm_configured,
    )
    return (200 if ready else 503), body


@router.get("/health")
def health(request: Request) -> JSONResponse:
    db = request.app.state.session_factory()
    try:
        status_code, body = read_health(db, request.app.state.settings)
    finally:
        db.close()
    return JSONResponse(status_code=status_code, content=body.model_dump())
