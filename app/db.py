"""数据库引擎与会话（个人本地 agent：默认 SQLite 单文件；Postgres 为企业部署备选，见 docs/08）。"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# 轻量列迁移（演示级）：create_all 不会为既有表补列
_COLUMN_MIGRATIONS = (
    ("missions", "provider_id", "VARCHAR(32)"),
    ("missions", "title", "VARCHAR(120)"),
    ("design_parameters", "payload", "JSON"),
    ("chat_sessions", "compacted_until", "INTEGER DEFAULT 0"),
    ("chat_sessions", "pinned", "BOOLEAN DEFAULT 0"),
    ("chat_sessions", "provider_id", "VARCHAR(32)"),
    ("chat_sessions", "model", "VARCHAR(120)"),
    ("chat_sessions", "reasoning_effort", "VARCHAR(16)"),
    ("chat_documents", "scope", "VARCHAR(16) DEFAULT 'session'"),
    ("chat_documents", "kind", "VARCHAR(16) DEFAULT 'document'"),
)


def init_db() -> None:
    from app import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(engine)
    for table, column, ddl in _COLUMN_MIGRATIONS:
        try:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        except Exception:  # noqa: BLE001 —— 列已存在
            pass


def new_session() -> Session:
    return SessionLocal()
