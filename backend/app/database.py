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


def ensure_video_owner_column(engine: Engine) -> None:
    """旧库只有视频表时补上归属列。正式迁移仍由学习档案负责人用 Alembic 合并。"""
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(videos)").fetchall()
        if not rows or any(row[1] == "owner_id" for row in rows):
            return
        connection.exec_driver_sql("ALTER TABLE videos ADD COLUMN owner_id VARCHAR(36)")


def ensure_question_metadata_columns(engine: Engine) -> None:
    """旧库的 questions 表补上检索元数据列。

    create_all 只建新表，不会给已存在的表加列。旧记录保持 NULL，
    读取时按契约呈现为 bm25，不伪称 hybrid。
    """
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(questions)").fetchall()
        if not rows:
            return
        existing = {row[1] for row in rows}
        if "retrieval_mode" not in existing:
            connection.exec_driver_sql("ALTER TABLE questions ADD COLUMN retrieval_mode VARCHAR(20)")
        if "retrieval_version" not in existing:
            connection.exec_driver_sql("ALTER TABLE questions ADD COLUMN retrieval_version VARCHAR(32)")
