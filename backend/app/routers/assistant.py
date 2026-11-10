"""悬浮助教的站内使用问答。范围只到产品用法，不涉及课程内容。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import assistant
from app.errors import AppError
from app.schemas import AssistantChatIn, AssistantChatOut

router = APIRouter(prefix="/api")


@router.post("/assistant/chat")
def chat(body: AssistantChatIn, request: Request) -> AssistantChatOut:
    messages = [{"role": item.role, "content": item.content.strip()} for item in body.messages]
    last = messages[-1]
    if last["role"] != "user":
        raise AppError(422, "INVALID_QUESTION", "最后一条消息必须是你提出的问题", False)
    if not last["content"]:
        raise AppError(422, "INVALID_QUESTION", "请输入你的问题", False)
    if len(last["content"]) > assistant.MAX_QUESTION_CHARS:
        raise AppError(422, "INVALID_QUESTION", "请输入1至300个字符的问题", False)
    if sum(len(item["content"]) for item in messages) > assistant.MAX_TOTAL_CHARS:
        raise AppError(422, "INVALID_QUESTION", "对话过长，请刷新页面重新开始", False)
    if not assistant.try_begin():
        raise AppError(429, "ASSISTANT_BUSY", "正在回答上一个问题，请稍后再试", True, {"Retry-After": "3"})
    try:
        reply = assistant.reply(messages, request.app.state.settings)
    finally:
        assistant.end()
    return AssistantChatOut(answer=reply.answer, mode=reply.mode)  # type: ignore[arg-type]
