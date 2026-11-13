import sqlite3
import pathlib
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.media import MediaInfo, _interpret, probe_media


def test_health_says_transcriber_is_missing(client):
    response = client.get("/api/health")
    body = response.json()
    expected_ok = (pathlib.Path("modules") / "transcriber" / "__init__.py").is_file()
    assert response.status_code == 503  # 单测关闭执行器，不能假称完整处理链已就绪。
    assert body["status"] == "not_ready"
    assert body["executor"] == "disabled"
    assert body["database"] == "ok"
    assert body["transcriber"] == ("ready" if expected_ok else "missing")
    assert body["llm_configured"] is False
    assert response.headers["x-request-id"]
    assert "detail" not in body


def test_four_tables_exist(client):
    connection = sqlite3.connect(client.app.state.settings.database_path)
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert {"videos", "segments", "chapters", "questions", "users", "sessions"} <= names


def test_missing_video_and_bad_id(client):
    missing = client.get("/api/videos/43b4b091-630e-4819-8f56-f20b9120c099")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "VIDEO_NOT_FOUND"
    assert "detail" not in missing.json()
    invalid = client.get("/api/videos/not-a-uuid")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_PARAMETER"


def test_upload_accepted_and_listed(client, monkeypatch):
    monkeypatch.setattr("app.media.probe_media", lambda *args, **kwargs: MediaInfo(3.5, "mp4", "h264", "aac"))
    payload = "分类模型评估".encode("utf-8")
    response = client.post("/api/videos", files={"file": ("分类模型评估.mp4", payload, "video/mp4")})
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "id",
        "title",
        "status",
        "processing_mode",
        "duration_sec",
        "size_bytes",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "elapsed_sec",
        "attempt",
        "error",
    }
    assert body["title"] == "分类模型评估"
    assert body["status"] == "queued"
    assert body["processing_mode"] == "audio_only"
    assert body["duration_sec"] == 3.5
    assert body["size_bytes"] == len(payload)
    assert body["elapsed_sec"] == 0
    assert body["attempt"] == 1
    assert body["error"] is None
    assert body["created_at"].endswith("Z")
    assert response.headers["location"] == f"/api/videos/{body['id']}"
    listed = client.get("/api/videos").json()
    assert listed["total"] == 1
    assert listed["limit"] == 20
    assert listed["offset"] == 0
    assert listed["items"][0]["id"] == body["id"]
    fetched = client.get(f"/api/videos/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_upload_too_large_leaves_no_file(client):
    client.app.state.settings = replace(client.app.state.settings, max_upload_bytes=8)
    response = client.post("/api/videos", files={"file": ("big.mp4", b"0123456789abcdef", "video/mp4")})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert client.get("/api/videos").json()["total"] == 0
    assert list((client.app.state.settings.data_dir / "tmp").glob("*")) == []


def test_upload_without_media_check_creates_no_record(client, monkeypatch):
    def boom(*args, **kwargs):
        raise AppError(503, "SERVICE_NOT_READY", "还没有安装 ffprobe，请系统工程师先准备 FFmpeg", True)

    monkeypatch.setattr("app.media.probe_media", boom)
    response = client.post("/api/videos", files={"file": ("a.mp4", b"abc", "video/mp4")})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"
    assert client.get("/api/videos").json()["total"] == 0


def test_missing_file_field(client):
    response = client.post("/api/videos")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"
    assert "detail" not in response.json()


def test_queue_full(client, make_video):
    for _ in range(3):
        make_video("queued")
    response = client.post("/api/videos", files={"file": ("a.mp4", b"abc", "video/mp4")})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUEUE_FULL"
    assert response.headers["retry-after"] == "10"
    assert client.get("/api/videos").json()["total"] == 3


def test_list_is_newest_first(client, make_video):
    older = make_video(created_at="2026-11-05T01:00:00Z")
    newer = make_video(created_at="2026-11-05T03:00:00Z")
    items = client.get("/api/videos").json()["items"]
    assert [item["id"] for item in items] == [newer, older]


def test_bad_paging(client):
    response = client.get("/api/videos?limit=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_transcript_and_summary_wait_until_ready(client, make_video):
    video_id = make_video("transcribing")
    transcript = client.get(f"/api/videos/{video_id}/transcript")
    summary = client.get(f"/api/videos/{video_id}/summary")
    assert transcript.status_code == 409
    assert transcript.json()["error"] == {
        "code": "VIDEO_NOT_READY",
        "message": "视频尚未处理完成，请稍后再试",
        "retryable": True,
    }
    assert summary.status_code == 409
    failed_id = make_video("failed", retryable=True)
    failed = client.get(f"/api/videos/{failed_id}/transcript")
    assert failed.status_code == 409
    assert failed.json()["error"]["retryable"] is False


def test_transcript_returns_segment_id_field_name(client, make_video):
    video_id = make_video("ready")
    from app.models import Segment

    segment_id = str(uuid4())
    db = client.app.state.session_factory()
    db.add(Segment(id=segment_id, video_id=video_id, start_sec=32.5, end_sec=39.0, text="精确率等于真正例除以真正例与假正例之和。"))
    db.commit()
    db.close()
    body = client.get(f"/api/videos/{video_id}/transcript").json()
    assert body["video_id"] == video_id
    assert body["segments"] == [
        {"id": segment_id, "start_sec": 32.5, "end_sec": 39.0, "text": "精确率等于真正例除以真正例与假正例之和。"}
    ]


def test_content_range(client, make_video):
    video_id = make_video("ready")
    full = client.get(f"/api/videos/{video_id}/content")
    assert full.status_code == 200
    assert full.headers["content-type"].startswith("video/mp4")
    assert full.headers["accept-ranges"] == "bytes"
    assert full.content == b"0123456789"
    partial = client.get(f"/api/videos/{video_id}/content", headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.headers["content-range"] == "bytes 0-3/10"
    assert partial.content == b"0123"
    multi = client.get(f"/api/videos/{video_id}/content", headers={"Range": "bytes=0-1,2-3"})
    assert multi.status_code == 200
    assert multi.content == b"0123456789"
    beyond = client.get(f"/api/videos/{video_id}/content", headers={"Range": "bytes=100-"})
    assert beyond.status_code == 416
    assert beyond.headers["content-range"] == "bytes */10"
    assert beyond.json()["error"]["code"] == "RANGE_NOT_SATISFIABLE"


def test_question_validation_and_not_ready(client, make_video):
    video_id = make_video("queued")
    blank = client.post(f"/api/videos/{video_id}/questions", json={"question": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "INVALID_QUESTION"
    extra = client.post(f"/api/videos/{video_id}/questions", json={"question": "幂等性是什么？", "history": []})
    assert extra.status_code == 422
    waiting = client.post(f"/api/videos/{video_id}/questions", json={"question": "幂等性是什么？"})
    assert waiting.status_code == 409
    ready_id = make_video("ready")
    missing = client.post(f"/api/videos/{ready_id}/questions", json={"question": "幂等性是什么？"})
    assert missing.status_code == 200
    assert missing.json()["answer_status"] == "not_found"
    assert missing.json()["citations"] == []


def test_retry_and_delete(client, make_video):
    queued_id = make_video("queued")
    rejected = client.post(f"/api/videos/{queued_id}/retry")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "RETRY_NOT_ALLOWED"
    busy = client.delete(f"/api/videos/{queued_id}")
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "VIDEO_BUSY"
    assert client.get(f"/api/videos/{queued_id}").status_code == 200

    failed_id = make_video("failed", retryable=False)
    blocked = client.post(f"/api/videos/{failed_id}/retry")
    assert blocked.status_code == 409

    retryable_id = make_video("failed", retryable=True)
    accepted = client.post(f"/api/videos/{retryable_id}/retry")
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["id"] == retryable_id
    assert body["status"] == "queued"
    assert body["attempt"] == 2
    assert body["error"] is None
    assert body["started_at"] is None

    removed = client.delete(f"/api/videos/{failed_id}")
    assert removed.status_code == 204
    assert removed.content == b""
    assert client.get(f"/api/videos/{failed_id}").status_code == 404
    second = client.delete(f"/api/videos/{failed_id}")
    assert second.status_code == 404


def test_restart_marks_unfinished_processing_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASK_EXECUTOR_ENABLED", "0")  # SYS：单测不开执行器
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    first = create_app()
    with TestClient(first) as client:
        processing_id = str(uuid4())
        queued_id = str(uuid4())
        settings = client.app.state.settings
        for video_id, status in ((processing_id, "transcribing"), (queued_id, "queued")):
            folder = settings.data_dir / "videos" / video_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "video.mp4"
            path.write_bytes(b"0123456789")
            from app.models import Video

            db = client.app.state.session_factory()
            from tests.conftest import sign_in

            owner_id = sign_in(client)
            db.add(
                Video(
                    id=video_id,
                    owner_id=owner_id,
                    title="示例课",
                    status=status,
                    processing_mode="audio_only",
                    duration_sec=30,
                    size_bytes=10,
                    created_at="2026-11-05T02:00:00Z",
                    updated_at="2026-11-05T02:00:00Z",
                    started_at="2026-11-05T02:00:01Z" if status == "transcribing" else None,
                    finished_at=None,
                    attempt=1,
                    error_code=None,
                    error_message=None,
                    error_retryable=None,
                    local_path=str(path),
                )
            )
            db.commit()
            db.close()
    first.state.engine.dispose()
    get_settings.cache_clear()
    second = create_app()
    with TestClient(second) as client:
        from tests.conftest import sign_in

        sign_in(client)
        processing = client.get(f"/api/videos/{processing_id}").json()
        queued = client.get(f"/api/videos/{queued_id}").json()
    second.state.engine.dispose()
    get_settings.cache_clear()
    assert processing["status"] == "failed"
    assert processing["error"]["code"] == "PROCESS_INTERRUPTED"
    assert processing["error"]["retryable"] is True
    assert queued["status"] == "queued"
    assert queued["error"] is None


def test_media_rules():
    streams = [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"},
    ]
    ok = _interpret({"format": {"format_name": "mov,mp4,m4a", "duration": "12.5"}, "streams": streams}, 1200)
    assert ok.duration_sec == 12.5
    with pytest.raises(AppError) as no_audio:
        _interpret({"format": {"format_name": "mp4", "duration": "3"}, "streams": streams[:1]}, 1200)
    assert no_audio.value.code == "AUDIO_REQUIRED"
    with pytest.raises(AppError) as wrong_codec:
        _interpret(
            {
                "format": {"format_name": "mp4", "duration": "3"},
                "streams": [
                    {"codec_type": "video", "codec_name": "hevc"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            },
            1200,
        )
    assert wrong_codec.value.code == "UNSUPPORTED_MEDIA"
    with pytest.raises(AppError) as too_long:
        _interpret({"format": {"format_name": "mp4", "duration": "1201"}, "streams": streams}, 1200)
    assert too_long.value.code == "DURATION_EXCEEDED"


def test_probe_reports_missing_ffprobe(tmp_path):
    with pytest.raises(AppError) as caught:
        probe_media(tmp_path / "missing.mp4", "ffprobe-not-installed")
    assert caught.value.status_code == 503
    assert caught.value.code == "SERVICE_NOT_READY"
