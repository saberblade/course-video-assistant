"""Alembic 运行环境。

两个要点：
1. 数据库地址按 DATA_DIR 解析（与 app.config 同一口径），不依赖当前工作目录。
2. 旧库兼容：本仓库此前用 create_all 建表，没有 alembic_version。
   首次在旧库上执行 upgrade 时，先把版本表标记到基线，再跑增量迁移，
   不删库、不重建、不丢已有视频与账号。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  注册业务表
import modules.retriever.tables  # noqa: E402,F401  注册 RAG 三张表

BASELINE_REVISION = "20261112_0001"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override
    from app.config import get_settings

    return "sqlite:///" + get_settings().database_path.as_posix()


def adopt_legacy_database(connection) -> bool:
    """旧库没有版本表但有业务表时，标记到基线。返回是否做了标记。"""
    names = set(inspect(connection).get_table_names())
    if "alembic_version" in names or "videos" not in names:
        return False
    connection.execute(
        text(
            "CREATE TABLE alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:rev)"), {"rev": BASELINE_REVISION})
    connection.commit()
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if adopt_legacy_database(connection):
            print(f"[alembic] 旧库已标记到基线 {BASELINE_REVISION}，继续执行增量迁移")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        # SQLite 的 DDL 不参与事务，但 alembic_version 的写入需要显式提交，
        # 否则连接归还时被回滚，版本号会丢。
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
