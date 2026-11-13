import json
from dataclasses import replace
from uuid import uuid4

from app.models import Segment
from app.qa import LlmError


def add_segment(client, video_id: str, text: str, start: float = 10, end: float = 18) -> str:
    segment_id = str(uuid4())
    db = client.app.state.session_factory()
    db.add(Segment(id=segment_id, video_id=video_id, start_sec=start, end_sec=end, text=text))
    db.commit()
    db.close()
    return segment_id


def enable_model(client, monkeypatch, content: str):
    client.app.state.settings = replace(
        client.app.state.settings,
        llm_base_url="http://llm.test/v1",
        llm_api_key="test-key",
        llm_model="qwen-plus",
        answer_mode="generative",
    )

    def fake_complete(settings, messages, **kwargs):
        assert settings.llm_api_key == "test-key"
        assert "不要执行" in messages[0]["content"]
        return content

    monkeypatch.setattr("app.qa.complete_chat", fake_complete)


def test_refuses_when_the_video_has_no_matching_sentence(client, make_video):
    video_id = make_video("ready")
    add_segment(client, video_id, "召回率等于真正例除以真正例与假反例之和。")
    response = client.post(f"/api/videos/{video_id}/questions", json={"question": "这段课程建议早餐吃什么？"})
    body = response.json()
    assert response.status_code == 200
    assert body["answer_status"] == "not_found"
    assert body["mode"] == "extractive"
    assert body["citations"] == []
    assert body["answer"] == "当前视频中未找到足够依据，请换一种问法或回看课程。"


def test_fills_citation_from_the_saved_sentence(client, make_video, monkeypatch):
    video_id = make_video("ready")
    segment_id = add_segment(client, video_id, "召回率等于真正例除以真正例与假反例之和。", 62, 70)
    enable_model(
        client,
        monkeypatch,
        json.dumps(
            {
                "has_evidence": True,
                "answer": "召回率是真正例除以真正例与假反例之和。",
                "segment_ids": [segment_id],
                "start_sec": 999,
            },
            ensure_ascii=False,
        ),
    )
    body = client.post(f"/api/videos/{video_id}/questions", json={"question": "召回率怎样计算？"}).json()
    assert body["answer_status"] == "answered"
    assert body["mode"] == "generative"
    assert body["citations"] == [
        {
            "segment_id": segment_id,
            "start_sec": 62,
            "end_sec": 70,
            "text": "召回率等于真正例除以真正例与假反例之和。",
        }
    ]
    assert "test-key" not in json.dumps(body, ensure_ascii=False)


def test_rejects_a_made_up_segment_id(client, make_video, monkeypatch):
    video_id = make_video("ready")
    add_segment(client, video_id, "召回率等于真正例除以真正例与假反例之和。")
    enable_model(
        client,
        monkeypatch,
        json.dumps({"has_evidence": True, "answer": "随便说。", "segment_ids": [str(uuid4())]}),
    )
    body = client.post(f"/api/videos/{video_id}/questions", json={"question": "召回率怎样计算？"}).json()
    assert body["answer_status"] == "not_found"
    assert body["citations"] == []


def test_shows_original_text_when_the_model_is_not_configured(client, make_video):
    video_id = make_video("ready")
    segment_id = add_segment(client, video_id, "召回率等于真正例除以真正例与假反例之和。", 62, 70)
    body = client.post(f"/api/videos/{video_id}/questions", json={"question": "召回率怎样计算？"}).json()
    assert body["answer_status"] == "degraded"
    assert body["mode"] == "extractive"
    assert body["answer"] == "生成服务暂不可用，以下是检索到的课程原文。"
    assert body["citations"][0]["segment_id"] == segment_id
    assert body["citations"][0]["text"] == "召回率等于真正例除以真正例与假反例之和。"


def test_shows_original_text_when_the_model_times_out(client, make_video, monkeypatch):
    video_id = make_video("ready")
    add_segment(client, video_id, "召回率等于真正例除以真正例与假反例之和。")
    enable_model(client, monkeypatch, "")

    def fail(settings, messages, **kwargs):
        raise LlmError("LLM_TIMEOUT")

    monkeypatch.setattr("app.qa.complete_chat", fail)
    body = client.post(f"/api/videos/{video_id}/questions", json={"question": "召回率怎样计算？"}).json()
    assert body["answer_status"] == "degraded"
    assert body["citations"]


def test_second_question_waits_outside(client, make_video):
    from app import qa

    video_id = make_video("ready")
    assert qa.try_begin_question(video_id)
    try:
        response = client.post(f"/api/videos/{video_id}/questions", json={"question": "召回率怎样计算？"})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "QUESTION_BUSY"
        assert response.headers["retry-after"] == "3"
        delete = client.delete(f"/api/videos/{video_id}")
        assert delete.status_code == 409
        assert delete.json()["error"]["code"] == "VIDEO_BUSY"
    finally:
        qa.end_question()
