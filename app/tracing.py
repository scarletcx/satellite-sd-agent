"""全链路 trace（docs/05 §7）：每步一条 jsonl，落 artifacts/<task_id>/trace.jsonl。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


def task_dir(task_id: str) -> Path:
    path = settings.artifacts_dir / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def trace(task_id: str, record: dict) -> dict:
    """追加一条 trace 记录（自动补 ts），返回落盘后的记录。"""
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with (task_dir(task_id) / "trace.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_trace(task_id: str) -> list[dict]:
    path = task_dir(task_id) / "trace.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
