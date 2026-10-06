"""数据库引擎与会话（骨架阶段默认 SQLite；目标形态 Postgres + pgvector，见 docs/08）。"""
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
