"""账号、会话和视频归属。密码只存 Argon2id 哈希，会话原文只放在 Cookie 里。"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Session as LoginSession
from app.models import User

_HASHER = PasswordHasher()
_USERNAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_FAILS: dict[tuple[str, str], list[float]] = {}
SESSION_COOKIE = "session"
csrf_header = APIKeyHeader(
    name="X-CSRF-Token",
    auto_error=False,
    scheme_name="CSRF",
    description="登录返回的 csrf_token。查看不用填；上传、提问、删除和退出要填。",
)
SESSION_HOURS = 24


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def validate_new_account(username: str, password: str, display_name: str) -> tuple[str, str]:
    if not _USERNAME.fullmatch(username.strip()):
        raise AppError(422, "INVALID_PARAMETER", "用户名需要3至32位字母、数字或下划线", False)
    if not 8 <= len(password) <= 128:
        raise AppError(422, "INVALID_PARAMETER", "密码需要8至128个字符", False)
    shown = display_name.strip()
    if not shown or len(shown) > 32:
        raise AppError(422, "INVALID_PARAMETER", "显示名需要1至32个字符", False)
    return normalize_username(username), shown


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def password_matches(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    parsed = urlparse(origin)
    allowed = {"127.0.0.1", "localhost", "testserver", request.url.hostname}
    if parsed.scheme in {"http", "https"} and parsed.hostname in allowed:
        return
    raise AppError(403, "ORIGIN_REJECTED", "这个页面不能发起登录", False)


def too_many_attempts(request: Request, username: str) -> bool:
    key = _attempt_key(request, username)
    now = time.monotonic()
    recent = [item for item in _FAILS.get(key, []) if now - item < 900]
    _FAILS[key] = recent
    return len(recent) >= 8


def record_failed_attempt(request: Request, username: str) -> None:
    key = _attempt_key(request, username)
    now = time.monotonic()
    recent = [item for item in _FAILS.get(key, []) if now - item < 900]
    recent.append(now)
    _FAILS[key] = recent


def clear_failed_attempts(request: Request, username: str) -> None:
    _FAILS.pop(_attempt_key(request, username), None)


def open_session(db: Session, user: User) -> tuple[LoginSession, str]:
    token = secrets.token_urlsafe(32)
    row = LoginSession(
        id=secrets.token_hex(16),
        user_id=user.id,
        token_hash=_digest(token),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=_later(SESSION_HOURS),
        created_at=_later(0),
    )
    db.add(row)
    db.commit()
    return row, token


def require_user(request: Request, db: Session) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _login_required()
    row = db.scalar(select(LoginSession).where(LoginSession.token_hash == _digest(token)))
    if row is None or row.expires_at <= _later(0):
        if row is not None:
            db.delete(row)
            db.commit()
        raise _login_required()
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise _login_required()
    request.state.current_user = user
    request.state.current_session = row
    return user


def require_csrf(request: Request) -> None:
    row = getattr(request.state, "current_session", None)
    provided = request.headers.get("x-csrf-token") or ""
    if row is None or not provided or not secrets.compare_digest(provided, row.csrf_token):
        raise AppError(403, "CSRF_FAILED", "页面校验未通过，请刷新后重试", False)


def owned_or_missing(video_owner_id: str | None, user_id: str) -> bool:
    return video_owner_id == user_id


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _attempt_key(request: Request, username: str) -> tuple[str, str]:
    host = request.client.host if request.client else ""
    return normalize_username(username), host


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _later(hours: int) -> str:
    moment = datetime.now(timezone.utc) + timedelta(hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _login_required() -> AppError:
    return AppError(401, "UNAUTHENTICATED", "请先登录", False)
