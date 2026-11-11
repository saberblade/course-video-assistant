"""注册、登录、恢复身份和退出。"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    csrf_header,
    check_origin,
    clear_failed_attempts,
    clear_session_cookie,
    hash_password,
    open_session,
    password_matches,
    record_failed_attempt,
    require_csrf,
    require_user,
    set_session_cookie,
    too_many_attempts,
    validate_new_account,
)
from app.clock import utc_now
from app.database import get_db
from app.errors import AppError
from app.models import User
from app.schemas import AuthOut, LoginIn, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth")


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    check_origin(request)
    username, display_name = validate_new_account(body.username, body.password, body.display_name)
    user = User(
        id=secrets.token_hex(16),
        username_normalized=username,
        display_name=display_name,
        password_hash=hash_password(body.password),
        is_active=1,
        created_at=utc_now(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "USERNAME_TAKEN", "这个用户名已经有人使用", False) from exc
    return JSONResponse(status_code=201, content=_user_out(user).model_dump())


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    check_origin(request)
    if too_many_attempts(request, body.username):
        raise AppError(429, "LOGIN_LIMITED", "尝试次数过多，请稍后再试", True, {"Retry-After": "60"})
    username = body.username.strip().casefold()
    user = db.scalar(select(User).where(User.username_normalized == username))
    if user is None or not user.is_active or not password_matches(user.password_hash, body.password):
        record_failed_attempt(request, body.username)
        raise AppError(401, "INVALID_CREDENTIALS", "用户名或密码不正确", False)
    clear_failed_attempts(request, body.username)
    row, token = open_session(db, user)
    response = JSONResponse(content=AuthOut(user=_user_out(user), csrf_token=row.csrf_token).model_dump())
    set_session_cookie(response, token)
    return response


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = require_user(request, db)
    row = request.state.current_session
    body = AuthOut(user=_user_out(user), csrf_token=row.csrf_token).model_dump()
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db), _csrf: str | None = Depends(csrf_header)) -> Response:
    require_user(request, db)
    require_csrf(request)
    db.delete(request.state.current_session)
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username_normalized, display_name=user.display_name)
