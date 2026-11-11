"""所有出错都走同一张小票：错误代码、说明、能不能再试、请求编号。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.headers = headers or {}


def error_payload(request: Request, code: str, message: str, retryable: bool) -> dict:
    request_id = getattr(request.state, "request_id", "")
    return {
        "error": {"code": code, "message": message, "retryable": retryable},
        "request_id": request_id,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, exc.code, exc.message, exc.retryable),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        code, message = _validation_message(request, exc)
        return JSONResponse(
            status_code=422,
            content=error_payload(request, code, message, False),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        app.state.logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(request, "INTERNAL_ERROR", "服务内部出错，请把请求编号交给后端排查", True),
        )


def _validation_message(request: Request, exc: RequestValidationError) -> tuple[str, str]:
    path = request.url.path
    if path.startswith("/api/auth/"):
        return "INVALID_PARAMETER", "账号或密码格式不正确"
    if path.endswith("/assistant/chat"):
        return "INVALID_QUESTION", "对话消息格式不正确"
    if path.endswith("/questions"):
        return "INVALID_QUESTION", "请输入1至300个字符的问题"
    for item in exc.errors():
        location = item.get("loc", ())
        if "file" in location:
            return "INVALID_PARAMETER", "请使用 file 字段上传一个视频文件"
        if "limit" in location or "offset" in location:
            return "INVALID_PARAMETER", "分页参数不正确"
    return "INVALID_PARAMETER", "请求参数不正确"
