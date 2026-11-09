"""服务入口。启动命令见 docs/BE-01-协议核对结论.md。"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, get_settings
from app.database import Base, make_engine, session_factory_for
from app.errors import register_error_handlers
from app.lifecycle import recover_interrupted
from app.models import Chapter, Question, Segment, Video  # noqa: F401  注册四张表
from app.routers import health, videos


def create_app() -> FastAPI:
    settings = get_settings()
    logger = logging.getLogger("course_review")
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    engine = make_engine(settings.database_path)
    session_factory = session_factory_for(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for name in ("tmp", "videos", "trash"):
            (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(engine)
        db = session_factory()
        try:
            recover_interrupted(db)
        finally:
            db.close()
        executor = None
        # 任务执行器默认开启；backend/tests 与联调可通过 TASK_EXECUTOR_ENABLED=0 关闭
        enabled = os.getenv("TASK_EXECUTOR_ENABLED", "1") != "0"
        if enabled:
            from app.executor import SerialTaskExecutor

            executor = SerialTaskExecutor(session_factory, logger)
            executor.start()
        app.state.task_executor = executor
        yield
        if executor is not None:
            executor.stop()
        engine.dispose()

    app = FastAPI(title="课程视频复习助手", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.logger = logger
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.queue_lock = threading.Lock()

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(videos.router)

    # 同源托管前端构建产物（契约03：托管frontend/dist）。未构建时跳过并记日志。
    dist_dir = PROJECT_ROOT / "frontend" / "dist"
    if (dist_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
        logger.info("static hosting served from %s", dist_dir)
    else:
        logger.info("frontend/dist not built yet, static hosting skipped")
    return app


app = create_app()
