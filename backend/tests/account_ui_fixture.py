"""Isolated browser-QA service. No production database or external model calls."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
target = Path(os.environ["ACCOUNT_UI_TEST_DIR"]).resolve()
if target.parent != (ROOT / "logs").resolve() or not target.name.startswith("account-ui-"):
    raise RuntimeError("QA data must use a fresh logs/account-ui-* directory")
if (target / "app.db").exists():
    raise RuntimeError("Refusing to reuse an existing database")
password = os.environ["ACCOUNT_UI_TEST_PASSWORD"]
os.environ.update(DATA_DIR=str(target), APP_VERSION=target.name, TASK_EXECUTOR_ENABLED="0", LLM_API_KEY="", LLM_BASE_URL="", LLM_MODEL="", ANSWER_MODE="extractive")

from app.auth import hash_password
from app.clock import utc_now
from app.database import Base
from app.main import app
from app.models import Chapter, Segment, User, Video

Base.metadata.create_all(app.state.engine)
with app.state.session_factory() as db:
    users = [User(id=str(uuid4()), username_normalized=name, display_name=display, password_hash=hash_password(password), is_active=1, created_at=utc_now()) for name, display in [("qa_alpha", "甲同学"), ("qa_beta", "乙同学")]]
    db.add_all(users)
    db.commit()
    media = Path(os.environ.get("ACCOUNT_UI_MEDIA", str(ROOT / "data" / "tmp" / "sample_lecture.mp4")))
    courses = [(users[0], "甲的私有课程"), (users[1], "乙的私有课程"), (users[0], "甲的另一门课程")]
    for user, title in courses:
        video_id = str(uuid4())
        destination = target / "videos" / f"{video_id}.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(media, destination)
        db.add(Video(id=video_id, owner_id=user.id, title=title, status="ready", processing_mode="audio_only", duration_sec=119.4, size_bytes=destination.stat().st_size, created_at=utc_now(), updated_at=utc_now(), started_at=utc_now(), finished_at=utc_now(), attempt=1, local_path=str(destination)))
        db.flush()
        segment_id = str(uuid4())
        db.add(Segment(id=segment_id, video_id=video_id, start_sec=0.0, end_sec=15.0, text="召回率是真正例除以真正例与假反例之和。"))
        db.add(Chapter(id=str(uuid4()), video_id=video_id, start_sec=0.0, end_sec=60.0, title="章节提要", text="召回率是真正例除以真正例与假反例之和。", segment_ids_json=json.dumps([segment_id])))
    db.commit()

if __name__ == "__main__":
    import uvicorn
    (target / "service.pid").write_text(str(os.getpid()), encoding="ascii")
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("ACCOUNT_UI_TEST_PORT", "18080")), log_level="warning")
