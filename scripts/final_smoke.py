"""Verify the prototype in fresh data, then restore into another fresh directory.

Uses only its own random accounts and media. Existing courses are never listed or deleted.
Example: python scripts/final_smoke.py --config .env.local --media path/to/demo.mp4
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    args = parser.parse_args()
    config = args.config.resolve()
    env = os.environ.copy()
    for line in config.read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("WHISPER_MODEL_DIR", "FFMPEG_BIN", "FFPROBE_BIN"):
        value = env.get(key)
        if value and not Path(value).is_absolute() and (config.parent / value).exists():
            env[key] = str((config.parent / value).resolve())
    env.setdefault("WHISPER_MODEL_DIR", str(config.parent / "models/faster-whisper-small"))
    run = ROOT / "logs" / f"final-smoke-{uuid4().hex[:10]}"
    run.mkdir(parents=True)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env.update(DATA_DIR=str(run / "data"), APP_PORT=str(port), TASK_EXECUTOR_ENABLED="1", COURSE_PYTHON=sys.executable, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    base = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(28)
    accounts = ["smoke_" + uuid4().hex[:16] for _ in range(2)]
    results = []
    server = None
    report = ROOT / "tests/evidence/final_runtime_20261112.json"
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    def record(name, **values):
        results.append({"check": name, "result": "passed", **values})
        print("PASS", name, flush=True)

    def command(arguments):
        result = subprocess.run(arguments, cwd=ROOT, env=env, capture_output=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(f"{Path(arguments[0]).name} failed: {result.stderr[-1800:]}")
        return result.stdout

    def start():
        nonlocal server
        Path(env["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
        command([sys.executable, "-m", "alembic", "upgrade", "head"])
        log = (run / f"server-{len(results)}.log").open("w", encoding="utf-8")
        server = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"), "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.close()
        deadline = time.monotonic() + 100
        with httpx.Client(base_url=base, trust_env=False, timeout=5) as client:
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Isolated server exited; inspect its local log")
                try:
                    response = client.get("/api/health")
                    if response.status_code == 200:
                        return response.json()
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
        raise RuntimeError("Actual transcription model did not become ready within 100s")

    def stop():
        if server is not None and server.poll() is None:
            command(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "deploy/stop.ps1")])
            server.wait(timeout=15)

    def signin(client, username, create=False):
        client.headers["Origin"] = base
        credentials = {"username": username, "password": password}
        if create:
            response = client.post("/api/auth/register", json={**credentials, "display_name": "原型验证"})
            assert response.status_code == 201
        response = client.post("/api/auth/login", json=credentials)
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]

    try:
        health = start()
        record("fresh_migration_and_real_model_warmup", health=health)
        with httpx.Client(base_url=base, trust_env=False, timeout=40) as a, httpx.Client(base_url=base, trust_env=False, timeout=40) as b:
            signin(a, accounts[0], create=True)
            signin(b, accounts[1], create=True)
            with args.media.open("rb") as stream:
                upload = a.post("/api/videos", files={"file": ("prototype-smoke.mp4", stream, "video/mp4")})
            assert upload.status_code == 202
            video_id = upload.json()["id"]
            began = time.monotonic()
            deadline = began + 240
            while time.monotonic() < deadline:
                video = a.get(f"/api/videos/{video_id}").json()
                if video["status"] == "ready":
                    break
                if video["status"] == "failed":
                    raise RuntimeError(f"Media processing failed: {video.get('error')}")
                time.sleep(1)
            assert video["status"] == "ready"
            transcript = a.get(f"/api/videos/{video_id}/transcript").json()["segments"]
            chapters = a.get(f"/api/videos/{video_id}/summary").json()["chapters"]
            assert transcript and chapters
            record("real_media_upload_transcription_chapters", seconds=round(time.monotonic()-began, 2), segments=len(transcript), chapters=len(chapters), sample_kind="synthetic")
            for suffix in ("", "/content", "/transcript", "/summary", "/questions", "/progress", "/review-records"):
                assert b.get(f"/api/videos/{video_id}{suffix}").status_code == 404
            assert b.get("/api/videos").json()["total"] == 0
            record("two_account_resource_isolation")
            saved = a.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "expected_version": 0, "position_sec": 30})
            assert saved.status_code == 200
            note = a.patch(f"/api/videos/{video_id}/chapters/{chapters[0]['id']}/review", json={"attempt": 1, "expected_version": 0, "saved": True, "reviewed": True, "note": "原型最终版恢复验证"})
            assert note.status_code == 200
            record("progress_and_notes_persisted")
            for _ in range(90):
                state = a.get("/api/health").json()
                if state["rag_indexes_ready"] >= 1:
                    break
                time.sleep(1)
            assert state["rag_indexes_ready"] >= 1
            question = "请依据原文解释：" + transcript[0]["text"][:100]
            answer = a.post(f"/api/videos/{video_id}/questions", json={"question": question}).json()
            assert answer["answer_status"] == "answered" and answer["retrieval_mode"] == "hybrid"
            segment_map = {item["id"]: item for item in transcript}
            assert answer["citations"] and all(item["text"] == segment_map[item["segment_id"]]["text"] for item in answer["citations"])
            negative = a.post(f"/api/videos/{video_id}/questions", json={"question": "课程推荐的烤箱温度与蛋糕烘焙时间分别是多少？"}).json()
            assert negative["answer_status"] == "not_found" and negative["citations"] == []
            assert a.get(f"/api/videos/{video_id}/questions").json()["total"] == 2
            record("real_embedding_generation_citations_refusal_history", retrieval_mode=answer["retrieval_mode"], citations=len(answer["citations"]))
        stop()
        record("owned_service_stop_with_real_data_dir")
        snapshot = json.loads(command([sys.executable, str(ROOT / "scripts/operations.py"), "backup", "--keep", "10000"]))["backup"]
        env["DATA_DIR"] = str(run / "restored-data")
        restored = json.loads(command([sys.executable, str(ROOT / "scripts/operations.py"), "restore", snapshot]))
        assert Path(restored["data_dir"]).exists()
        record("verified_backup_and_clean_directory_restore")
        health = start()
        with httpx.Client(base_url=base, trust_env=False, timeout=40) as client:
            signin(client, accounts[0])
            progress = client.get(f"/api/videos/{video_id}/progress").json()
            assert progress["position_sec"] == 30
            notes = client.get(f"/api/videos/{video_id}/review-records").json()
            assert notes["items"][0]["note"] == "原型最终版恢复验证"
            assert client.get(f"/api/videos/{video_id}/questions").json()["total"] == 2
            assert client.get(f"/api/videos/{video_id}/content", headers={"Range": "bytes=0-31"}).status_code == 206
            assert health["rag_indexes_ready"] >= 1
            record("restored_login_media_progress_notes_history_vectors")
        stop()
    finally:
        if server is not None and server.poll() is None:
            try:
                stop()
            except Exception:
                server.terminate()
                server.wait(timeout=15)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"source_commit": revision, "scope": "prototype, synthetic media; no formal lecture quality claim", "checks": results, "completed": len(results) == 8}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evidence:", report)


if __name__ == "__main__":
    main()
