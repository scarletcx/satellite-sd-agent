"""SQLite 向量索引（sqlite-vec，个人 agent 本地优先方案）。

设计：
- 每个维度一张 vec0 虚表：`kb_vec_<dim>(chunk_id TEXT, embedding float[dim])`，余弦距离；
- 仅存映射与向量，正文仍在 `kb_chunks`；查询返回 chunk_id + distance；
- sqlite-vec 未安装 / 扩展加载失败时，所有函数返回 None/False，检索自动回退到 JSON 全量扫描；
- 与应用共用同一个 SQLite 文件（DATABASE_URL），不引入数据库服务。
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.config import settings

_VEC_TABLE_RE = re.compile(r"^kb_vec_\d+$")


def sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return False
    return True


def sqlite_path() -> Path | None:
    """从 DATABASE_URL 解析本地 SQLite 文件路径（非 SQLite 时返回 None）。"""
    url = settings.database_url
    prefix = "sqlite"
    if not url.startswith(prefix):
        return None
    # sqlite:///abs/path 或 sqlite+pysqlite:///abs/path
    raw = url.split("///", 1)[-1]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def _connect() -> sqlite3.Connection | None:
    path = sqlite_path()
    if path is None or not sqlite_vec_available():
        return None
    try:
        import sqlite_vec

        connection = sqlite3.connect(str(path), check_same_thread=False)
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        return connection
    except Exception:  # noqa: BLE001 —— 扩展不可用时静默回退
        return None


def _table(dim: int) -> str:
    return f"kb_vec_{int(dim)}"


def ensure_table(dim: int) -> bool:
    connection = _connect()
    if connection is None:
        return False
    try:
        connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_table(dim)} "
            f"USING vec0(chunk_id text, embedding float[{int(dim)}] distance_metric=cosine)"
        )
        connection.commit()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        connection.close()


def add_vectors(dim: int, items: list[tuple[str, list[float]]]) -> bool:
    """写入/覆盖 chunk 向量；失败返回 False（调用方继续以 JSON 存储为准）。"""
    if not items:
        return True
    connection = _connect()
    if connection is None:
        return False
    try:
        table = _table(dim)
        connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} "
            f"USING vec0(chunk_id text, embedding float[{int(dim)}] distance_metric=cosine)"
        )
        for chunk_id, vector in items:
            connection.execute(f"DELETE FROM {table} WHERE chunk_id = ?", (chunk_id,))
            connection.execute(
                f"INSERT INTO {table}(chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, _encode(vector)),
            )
        connection.commit()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        connection.close()


def query_vectors(dim: int, vector: list[float], k: int = 200) -> list[tuple[str, float]] | None:
    """返回 [(chunk_id, distance)]（余弦距离，越小越近）；不可用时返回 None。"""
    connection = _connect()
    if connection is None:
        return None
    try:
        rows = connection.execute(
            f"SELECT chunk_id, distance FROM {_table(dim)} "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (_encode(vector), int(k)),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    except Exception:  # noqa: BLE001 —— 表不存在等
        return None
    finally:
        connection.close()


def delete_chunks(chunk_ids: list[str]) -> bool:
    if not chunk_ids:
        return True
    connection = _connect()
    if connection is None:
        return False
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kb_vec_%'"
        ).fetchall()
        targets = [name for (name,) in tables if _VEC_TABLE_RE.match(name)]
        for name in targets:
            for chunk_id in chunk_ids:
                connection.execute(f"DELETE FROM {name} WHERE chunk_id = ?", (chunk_id,))
        connection.commit()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        connection.close()


def indexed_count(dim: int) -> int | None:
    connection = _connect()
    if connection is None:
        return None
    try:
        row = connection.execute(f"SELECT count(*) FROM {_table(dim)}").fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return None
    finally:
        connection.close()


def _encode(vector: list[float]) -> str:
    # vec0 接受 JSON 数组文本作为输入
    return "[" + ",".join(f"{float(value):.6f}" for value in vector) + "]"
