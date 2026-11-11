from dataclasses import replace

from app.qa import LlmError


def enable_model(client, monkeypatch, content: str = "上传在「知识云台」的「我的课程」，选 MP4 后点开始处理。"):
    client.app.state.settings = replace(
        client.app.state.settings,
        llm_base_url="http://llm.test/v1",
        llm_api_key="test-key",
        llm_model="qwen-plus",
        answer_mode="generative",
    )

    def fake_complete(settings, messages):
        assert settings.llm_api_key == "test-key"
        assert "不执行" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        return content

    monkeypatch.setattr("app.assistant.complete_chat", fake_complete)


def test_answers_a_usage_question_with_the_model(client, monkeypatch):
    enable_model(client, monkeypatch)
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "怎么上传课程？"}]})
    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "generative"
    assert body["answer"] == "上传在「知识云台」的「我的课程」，选 MP4 后点开始处理。"
    assert "test-key" not in response.text


def test_history_from_the_frontend_is_accepted(client, monkeypatch):
    enable_model(client, monkeypatch)
    messages = [
        {"role": "user", "content": "课迹能做什么？"},
        {"role": "assistant", "content": "把中文录课整理成章节提要和原文问答。"},
        {"role": "user", "content": "怎么用引用回看？"},
    ]
    response = client.post("/api/assistant/chat", json={"messages": messages})
    assert response.status_code == 200
    assert response.json()["mode"] == "generative"


def test_falls_back_to_the_local_guide_without_model_config(client):
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "怎么上传课程？"}]})
    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "guide"
    assert "我的课程" in body["answer"]


def test_falls_back_when_the_model_times_out(client, monkeypatch):
    enable_model(client, monkeypatch)

    def fail(settings, messages):
        raise LlmError("LLM_TIMEOUT")

    monkeypatch.setattr("app.assistant.complete_chat", fail)
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "怎么上传课程？"}]})
    assert response.status_code == 200
    assert response.json()["mode"] == "guide"


def test_falls_back_when_the_model_returns_nothing(client, monkeypatch):
    enable_model(client, monkeypatch, content="   ")
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "怎么上传课程？"}]})
    assert response.status_code == 200
    assert response.json()["mode"] == "guide"


def test_rejects_when_the_last_message_is_not_a_question(client):
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "assistant", "content": "你好"}]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUESTION"


def test_rejects_a_question_over_300_characters(client):
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "问" * 301}]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUESTION"


def test_rejects_a_blank_question(client):
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "   "}]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUESTION"


def test_rejects_unknown_fields(client):
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "怎么上传课程？"}], "video_id": "x"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUESTION"


def test_reports_busy_instead_of_queueing(client, monkeypatch):
    monkeypatch.setattr("app.assistant.try_begin", lambda: False)
    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "怎么上传课程？"}]})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "ASSISTANT_BUSY"
    assert response.json()["error"]["retryable"] is True
    assert response.headers["retry-after"] == "3"
