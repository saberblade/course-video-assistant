"""Regression checks for delivery blockers, using isolated data and no paid API calls."""
import asyncio
from dataclasses import replace
import importlib.util
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from app import qa
from app.executor import SerialTaskExecutor
from app.config import PROJECT_ROOT, get_settings


@pytest.mark.parametrize("flag", ["false", "true", 0, 1, None, [], {}])
def test_non_boolean_model_evidence_never_becomes_answer(client, make_video, monkeypatch, flag):
    from test_questions import add_segment, enable_model
    video = make_video("ready")
    segment = add_segment(client, video, "召回率衡量真实正类被找出的比例。")
    enable_model(client, monkeypatch, json.dumps({"has_evidence": flag, "answer": "有依据", "segment_ids": [segment]}))
    response = client.post(f"/api/videos/{video}/questions", json={"question": "召回率衡量什么？"})
    assert response.status_code == 200
    assert response.json()["answer_status"] == "degraded"
    assert response.json()["citations"][0]["segment_id"] == segment


def test_slow_stream_is_cancelled_with_retrieval_in_same_budget(client, monkeypatch):
    settings = replace(client.app.state.settings, llm_base_url="https://model.test/v1", llm_api_key="not-real", llm_total_deadline_seconds=0.15)
    piece = SimpleNamespace(id="real-segment", text="召回率用于评价召回。", start_sec=1, end_sec=4)
    def retrieve(*args):
        time.sleep(0.07)
        return [SimpleNamespace(segments=[piece])], "bm25", None
    monkeypatch.setattr(qa, "_retrieve", retrieve)
    cancelled = []
    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                for _ in range(100):
                    await asyncio.sleep(0.02)
                    yield b" "
            finally:
                cancelled.append(True)
    async def handler(request):
        return httpx.Response(200, stream=Trickle())
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda: original(transport=httpx.MockTransport(handler)))
    began = time.monotonic()
    result = qa.draft_answer([], "召回率？", 5, settings)
    assert result.answer_status == "degraded"
    assert result.citations[0].segment_id == "real-segment"
    assert time.monotonic() - began < 0.6
    assert cancelled


def test_queue_survives_claim_and_failure_persistence_errors(monkeypatch):
    executor = SerialTaskExecutor(lambda: None, logging.getLogger("test.queue"))
    executor._idle_wait = 0.001
    claims = iter([RuntimeError("locked"), "broken", "next"])
    processed = []
    def claim():
        item = next(claims)
        if isinstance(item, Exception):
            raise item
        return item
    def process(video):
        processed.append(video)
        if video == "broken":
            raise RuntimeError("write failed")
        executor._stop.set()
    def fail(*args):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(executor, "_claim_next", claim)
    monkeypatch.setattr(executor, "_process", process)
    monkeypatch.setattr(executor, "_fail", fail)
    thread = threading.Thread(target=executor._run)
    thread.start()
    thread.join(1)
    executor._stop.set()
    assert not thread.is_alive()
    assert processed == ["broken", "next"]


def test_drain_rejects_new_writes_and_health_exposes_real_busy(client):
    marker = client.app.state.settings.data_dir / ".draining"
    marker.write_text("test", encoding="utf-8")
    assert qa.try_begin_question("test")
    try:
        health = client.get("/api/health").json()
        assert health["draining"] and health["question_busy"]
        assert health["executor"] == "disabled"
        response = client.post("/api/auth/logout")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_DRAINING"
    finally:
        qa.end_question()
        marker.unlink()
    assert not client.get("/api/health").json()["question_busy"]


def test_transient_failure_write_is_retried_before_next_claim(monkeypatch):
    executor = SerialTaskExecutor(lambda: None, logging.getLogger("test.queue.retry"))
    executor._idle_wait = 0.001
    claims = iter(["broken", "healthy"])
    writes = []
    monkeypatch.setattr(executor, "_claim_next", lambda: next(claims))
    def process(video):
        if video == "broken":
            raise RuntimeError("task failed")
        executor._stop.set()
    def fail(video, *args):
        writes.append(video)
        if len(writes) == 1:
            raise RuntimeError("temporary lock")
    monkeypatch.setattr(executor, "_process", process)
    monkeypatch.setattr(executor, "_fail", fail)
    executor._run()
    assert writes == ["broken", "broken"]
    assert executor._pending_failures == {}


def test_restoring_elsewhere_relocates_media_paths(operations):
    ops = operations
    data = ops.data_directory()
    with sqlite3.connect(data / "app.db") as db:
        db.execute("CREATE TABLE videos (id TEXT, local_path TEXT)")
        db.execute("INSERT INTO videos VALUES ('one',?)", (str(data / "media.bin"),))
    db.close()
    snapshot = ops.backup()["backup"]
    other_data = ops.ROOT / "restored-data"
    # Test a genuinely different configured location, rather than overwriting in place.
    from unittest.mock import patch
    with patch.dict("os.environ", {"DATA_DIR": str(other_data)}):
        get_settings.cache_clear()
        ops.restore(snapshot)
        with sqlite3.connect(other_data / "app.db") as restored:
            path = restored.execute("SELECT local_path FROM videos").fetchone()[0]
        restored.close()
        assert Path(path) == other_data / "media.bin"
        assert Path(path).read_bytes() == b"original media"
    get_settings.cache_clear()


@pytest.fixture()
def operations(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("delivery_ops", PROJECT_ROOT / "scripts/operations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setenv("DATA_DIR", str(root / "custom-data"))
    get_settings.cache_clear()
    for folder in ("backend", "modules", "scripts", "deploy", "migrations", "frontend/dist"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for name in ("alembic.ini", "requirements.lock.txt", ".env.example", "frontend/package.json", "frontend/package-lock.json"):
        (root / name).write_text("example", encoding="utf-8")
    data = module.data_directory()
    data.mkdir()
    with sqlite3.connect(data / "app.db") as db:
        db.execute("CREATE TABLE records (value TEXT)")
        db.execute("INSERT INTO records VALUES ('saved')")
    db.close()
    (data / "media.bin").write_bytes(b"original media")
    (root / "frontend/dist/index.html").write_text("original UI", encoding="utf-8")
    monkeypatch.setattr(module, "assert_offline", lambda port: None)
    yield module
    get_settings.cache_clear()


def test_snapshot_restores_exact_tree_and_preserves_previous_state(operations):
    ops = operations
    snapshot = ops.backup(keep=1)["backup"]
    data = ops.data_directory()
    (data / "media.bin").write_bytes(b"damaged")
    (data / "extra.bin").write_bytes(b"created after backup")
    restored = ops.restore(snapshot)
    assert (data / "media.bin").read_bytes() == b"original media"
    assert not (data / "extra.bin").exists()
    retained = Path(restored["retained"][0])
    assert (retained / "extra.bin").exists()
    assert (retained / "media.bin").read_bytes() == b"damaged"
    safety = ops.ROOT / "backups/pre_restore_manual"
    ops.copy_tree(snapshot, safety)
    ops.backup(keep=1)
    assert retained.exists()
    assert (safety / "manifest.json").exists()
    assert len(list((ops.ROOT / "backups").glob("*/manifest.json"))) == 2


def test_tampered_backup_is_refused_without_changing_data(operations):
    snapshot = Path(operations.backup()["backup"])
    (snapshot / "data/media.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        operations.restore(snapshot)
    assert (operations.data_directory() / "media.bin").read_bytes() == b"original media"


def test_restore_failure_rolls_back_both_trees(operations, monkeypatch):
    snapshot = Path(operations.backup()["backup"])
    data = operations.data_directory()
    (data / "media.bin").write_bytes(b"current")
    real_replace = operations.os.replace
    def failing_replace(source, target):
        if ".dist.restore_" in str(source):
            raise PermissionError("dist is locked")
        return real_replace(source, target)
    monkeypatch.setattr(operations.os, "replace", failing_replace)
    with pytest.raises(PermissionError):
        operations.restore(snapshot)
    assert (data / "media.bin").read_bytes() == b"current"
    assert (operations.ROOT / "frontend/dist/index.html").read_text() == "original UI"


@pytest.mark.parametrize("payload", ["not-json", [], {"data":[{"index":"0","embedding":[1,0]}]}, {"data":[{"index":0,"embedding":[[1],0]}]}, {"data":[{"index":0,"embedding":["invalid",0]}]}])
def test_malformed_embedding_is_a_controlled_failure(monkeypatch, payload):
    from modules.retriever import embedding
    config = embedding.EmbeddingConfig("https://model.test/v1", "not-real", "test", 2, 10, 1)
    response = httpx.Response(200, text=payload) if isinstance(payload, str) else httpx.Response(200, json=payload)
    monkeypatch.setattr(embedding, "post_before", lambda *args, **kwargs: response)
    with pytest.raises(embedding.EmbeddingError):
        embedding.BailianEmbeddingClient(config).embed(["text"], 1)
