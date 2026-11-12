"""学习档案：播放进度、章节标记与备注、历史问答。

覆盖契约 02 的并发、越权与快照语义，全部走真实 HTTP 路由。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import PlaybackProgress, ReviewRecord


@pytest.fixture()
def make_chapter(client):
    def _make(video_id: str, title: str = "00:00 章节提要", start: float = 0.0, end: float = 60.0):
        from app.models import Chapter

        chapter_id = str(uuid4())
        db = client.app.state.session_factory()
        db.add(
            Chapter(
                id=chapter_id,
                video_id=video_id,
                start_sec=start,
                end_sec=end,
                title=title,
                text="这一节讲了召回率与精确率的区别。",
                segment_ids_json="[]",
            )
        )
        db.commit()
        db.close()
        return chapter_id

    return _make


# ---------------- 播放进度 ----------------


def test_progress_is_empty_before_any_save(client, make_video):
    video_id = make_video("ready")

    response = client.get(f"/api/videos/{video_id}/progress")

    assert response.status_code == 200
    assert response.json() == {
        "video_id": video_id,
        "attempt": 1,
        "position_sec": 0.0,
        "furthest_sec": 0.0,
        "version": 0,
        "updated_at": "",
        "saved": False,
    }


def test_progress_create_then_update_keeps_furthest(client, make_video):
    video_id = make_video("ready")

    created = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 26.0, "expected_version": 0})
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert created.json()["position_sec"] == 26.0
    assert created.json()["furthest_sec"] == 26.0

    # 回看：位置后退，最远位置保留最大值。
    back = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 12.0, "expected_version": 1})
    assert back.status_code == 200, back.text
    assert back.json()["version"] == 2
    assert back.json()["position_sec"] == 12.0
    assert back.json()["furthest_sec"] == 26.0

    read = client.get(f"/api/videos/{video_id}/progress")
    assert read.json()["position_sec"] == 12.0
    assert read.json()["version"] == 2


def test_progress_stale_version_is_rejected(client, make_video):
    video_id = make_video("ready")
    client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 10.0, "expected_version": 0})

    stale = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 20.0, "expected_version": 0})

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    # 冲突不能写坏已有记录。
    assert client.get(f"/api/videos/{video_id}/progress").json()["position_sec"] == 10.0


def test_progress_rejects_old_attempt_and_out_of_range(client, make_video):
    video_id = make_video("ready")

    old_attempt = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 2, "position_sec": 10.0, "expected_version": 0})
    too_far = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 181.0, "expected_version": 0})
    negative = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": -1.0, "expected_version": 0})

    assert old_attempt.status_code == 409
    assert old_attempt.json()["error"]["code"] == "STALE_ATTEMPT"
    assert too_far.status_code == 422
    assert negative.status_code == 422


def test_progress_of_other_users_video_is_404(client, make_video):
    video_id = make_video("ready", owner_id=None)

    response = client.get(f"/api/videos/{video_id}/progress")

    assert response.status_code == 404


def test_progress_requires_csrf(client, make_video):
    video_id = make_video("ready")
    token = client.headers.pop("X-CSRF-Token")

    try:
        response = client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 5.0, "expected_version": 0})
    finally:
        client.headers["X-CSRF-Token"] = token

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


# ---------------- 章节标记与备注 ----------------


def test_chapter_review_partial_update_keeps_other_fields(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    url = f"/api/videos/{video_id}/chapters/{chapter_id}/review"

    created = client.patch(url, json={"attempt": 1, "expected_version": 0, "saved": True, "note": "召回率还想再看"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["saved"] is True
    assert body["note"] == "召回率还想再看"
    assert body["reviewed"] is False
    assert body["resolved"] is False
    assert body["version"] == 1
    assert body["is_stale"] is False

    marked = client.patch(url, json={"attempt": 1, "expected_version": 1, "reviewed": True})
    assert marked.status_code == 200, marked.text
    body = marked.json()
    # 只改 reviewed，不能把已有的 saved 与备注清掉。
    assert body["reviewed"] is True
    assert body["saved"] is True
    assert body["note"] == "召回率还想再看"
    assert body["version"] == 2

    removed = client.patch(url, json={"attempt": 1, "expected_version": 2, "saved": False, "resolved": False, "note": ""})
    assert removed.status_code == 200, removed.text
    body = removed.json()
    # 移出清单保留独立 reviewed 标记。
    assert body["saved"] is False
    assert body["note"] == ""
    assert body["reviewed"] is True


def test_chapter_review_requires_a_changed_field(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)

    response = client.patch(
        f"/api/videos/{video_id}/chapters/{chapter_id}/review",
        json={"attempt": 1, "expected_version": 0},
    )

    assert response.status_code == 422


def test_chapter_review_stale_version_and_unknown_chapter(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    url = f"/api/videos/{video_id}/chapters/{chapter_id}/review"
    client.patch(url, json={"attempt": 1, "expected_version": 0, "saved": True})

    stale = client.patch(url, json={"attempt": 1, "expected_version": 0, "saved": False})
    missing = client.patch(
        f"/api/videos/{video_id}/chapters/{uuid4()}/review",
        json={"attempt": 1, "expected_version": 0, "saved": True},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


def test_chapter_review_rejects_unknown_field_and_long_note(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    url = f"/api/videos/{video_id}/chapters/{chapter_id}/review"

    unknown = client.patch(url, json={"attempt": 1, "expected_version": 0, "mastered": True})
    long_note = client.patch(url, json={"attempt": 1, "expected_version": 0, "note": "字" * 2001})

    assert unknown.status_code == 422
    assert long_note.status_code == 422


def test_review_records_are_isolated_and_listed(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    client.patch(
        f"/api/videos/{video_id}/chapters/{chapter_id}/review",
        json={"attempt": 1, "expected_version": 0, "saved": True, "note": "待复习"},
    )

    listing = client.get("/api/me/review-records?status=open")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    item = listing.json()["items"][0]
    assert item["video_id"] == video_id
    assert item["note"] == "待复习"
    assert item["is_stale"] is False


def test_my_review_records_rejects_bad_status(client):
    response = client.get("/api/me/review-records?status=done")
    assert response.status_code == 422


def test_old_attempt_records_are_marked_stale(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    client.patch(
        f"/api/videos/{video_id}/chapters/{chapter_id}/review",
        json={"attempt": 1, "expected_version": 0, "saved": True, "note": "旧批次备注"},
    )
    # 模拟重新处理：视频 attempt 前进，旧批次记录应标 is_stale。
    db = client.app.state.session_factory()
    from app.models import Video

    video = db.get(Video, video_id)
    video.attempt = 2
    db.commit()
    db.close()

    listing = client.get("/api/me/review-records?status=all")

    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["is_stale"] is True
    assert listing.json()["items"][0]["note"] == "旧批次备注"


def test_editing_other_users_record_is_404(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    created = client.patch(
        f"/api/videos/{video_id}/chapters/{chapter_id}/review",
        json={"attempt": 1, "expected_version": 0, "saved": True},
    ).json()

    db = client.app.state.session_factory()
    from app.models import User

    other = User(
        id=str(uuid4()),
        username_normalized="other_user",
        display_name="另一个账号",
        password_hash="x",
        is_active=1,
        created_at="2026-11-12T00:00:00Z",
    )
    db.add(other)
    db.commit()
    row = db.get(ReviewRecord, created["id"])
    row.user_id = other.id
    db.commit()
    db.close()

    response = client.patch(f"/api/me/review-records/{created['id']}", json={"expected_version": 0, "note": "改"})

    assert response.status_code == 404


def test_deleting_video_cleans_profile_rows(client, make_video, make_chapter):
    video_id = make_video("ready")
    chapter_id = make_chapter(video_id)
    client.put(f"/api/videos/{video_id}/progress", json={"attempt": 1, "position_sec": 30.0, "expected_version": 0})
    client.patch(
        f"/api/videos/{video_id}/chapters/{chapter_id}/review",
        json={"attempt": 1, "expected_version": 0, "saved": True},
    )

    deleted = client.delete(f"/api/videos/{video_id}")

    assert deleted.status_code == 204
    db = client.app.state.session_factory()
    assert db.scalar(select(func.count()).select_from(PlaybackProgress).where(PlaybackProgress.video_id == video_id)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewRecord).where(ReviewRecord.video_id == video_id)) == 0
    db.close()


# ---------------- 历史问答 ----------------


def test_question_history_is_paginated_newest_first(client, make_video):
    video_id = make_video("ready")
    for index in range(3):
        client.post(f"/api/videos/{video_id}/questions", json={"question": f"第{index}个问题"})

    first_page = client.get(f"/api/videos/{video_id}/questions?limit=2&offset=0")
    second_page = client.get(f"/api/videos/{video_id}/questions?limit=2&offset=2")

    assert first_page.status_code == 200
    body = first_page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    ids = [item["id"] for item in body["items"] + second_page.json()["items"]]
    assert len(ids) == len(set(ids))
    # 稳定倒序：第一页的第一条不早于第二条。
    assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]


def test_question_history_is_isolated_by_owner(client, make_video):
    video_id = make_video("ready", owner_id=None)

    response = client.get(f"/api/videos/{video_id}/questions")

    assert response.status_code == 404


def test_question_history_works_while_video_is_processing(client, make_video):
    video_id = make_video("transcribing")

    response = client.get(f"/api/videos/{video_id}/questions")

    assert response.status_code == 200
    assert response.json()["total"] == 0
