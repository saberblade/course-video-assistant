import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASK_EXECUTOR_ENABLED", "0")  # SYS：单测不开执行器，避免真实转写竞态
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    application.state.engine.dispose()
    get_settings.cache_clear()


@pytest.fixture()
def make_video(client):
    def _make(status="queued", *, retryable=True, created_at="2026-11-05T02:00:00Z"):
        from app.models import Video

        settings = client.app.state.settings
        video_id = str(uuid4())
        folder = settings.data_dir / "videos" / video_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "video.mp4"
        path.write_bytes(b"0123456789")
        started_at = None
        finished_at = None
        error_code = None
        error_message = None
        error_retryable = None
        if status in ("transcribing", "indexing", "ready", "failed"):
            started_at = "2026-11-05T02:00:01Z"
        if status == "failed":
            finished_at = "2026-11-05T02:00:20Z"
            error_code = "NO_SPEECH" if not retryable else "PROCESS_INTERRUPTED"
            error_message = "未识别到有效讲课语音，请更换清晰中文视频" if not retryable else "上次处理因服务重启中断，可重试"
            error_retryable = 0 if not retryable else 1
        db = client.app.state.session_factory()
        db.add(
            Video(
                id=video_id,
                title="示例课",
                status=status,
                processing_mode="audio_only",
                duration_sec=180,
                size_bytes=10,
                created_at=created_at,
                updated_at=created_at,
                started_at=started_at,
                finished_at=finished_at,
                attempt=1,
                error_code=error_code,
                error_message=error_message,
                error_retryable=error_retryable,
                local_path=str(path),
            )
        )
        db.commit()
        db.close()
        return video_id

    return _make
