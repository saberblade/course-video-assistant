"""连接 SQLite。视频文件不放进数据库，数据库只记账。"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


def make_engine(database_path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database_path, check_same_thread=False, timeout=30)

    # creator 指向文件库，但 sqlite:// 会默认选用 SingletonThreadPool；
    # 超过其线程容量时会关闭仍在使用的连接。每次借用独立连接，归还后关闭。
    engine = create_engine("sqlite://", creator=connect, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_db(request: Request) -> Generator[Session, None, None]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def session_factory_for(engine: Engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
