"""任务服务：创建（含后台调度）、列表、快照、重命名；供 API 与聊天工具复用。"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone

from app.db import new_session
from app.models import Mission, ReviewGate
from app.orchestrator.ids import next_mission_id


class MissionError(LookupError):
    def __init__(self, message: str, *, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


def default_title(goal: str) -> str:
    first = (goal or "").strip().splitlines()[0] if (goal or "").strip() else "未命名任务"
    return first[:40]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _launch(task_id: str) -> None:
    """任务流水线在后台线程执行（本地单用户，无需任务队列）。"""
    from app.orchestrator import engine

    def runner() -> None:
        asyncio.run(engine.run_mission(task_id))

    threading.Thread(target=runner, daemon=True, name=f"mission-{task_id}").start()


def create_mission(*, goal: str, constraints: dict | None = None,
                   provider_id: str | None = None, title: str | None = None) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise MissionError("任务目标不能为空")
    with new_session() as session:
        task_id = next_mission_id(session)
        row = Mission(
            id=task_id, goal=goal,
            title=(title or "").strip()[:120] or None,
            constraints=dict(constraints or {}),
            provider_id=provider_id or None,
            status="queued",
        )
        session.add(row)
        session.commit()
        created_at = row.created_at
    _launch(task_id)
    return {"task_id": task_id, "title": title or default_title(goal),
            "status": "queued", "created_at": _iso(created_at)}


def list_missions(status: str | None = None, limit: int = 50) -> list[dict]:
    with new_session() as session:
        query = session.query(Mission)
        if status:
            query = query.filter(Mission.status == status)
        rows = (query.order_by(Mission.created_at.desc(), Mission.id.desc())
                .limit(limit).all())
        return [
            {
                "task_id": row.id,
                "title": row.title or default_title(row.goal),
                "goal": row.goal,
                "status": row.status,
                "current_step": row.current_step,
                "cost_estimate_cny": row.cost_estimate_cny,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in rows
        ]


def mission_snapshot(task_id: str) -> dict:
    with new_session() as session:
        row = session.get(Mission, task_id)
        if row is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        gates = (session.query(ReviewGate)
                 .filter(ReviewGate.mission_id == task_id, ReviewGate.action.is_(None))
                 .all())
        return {
            "task_id": row.id,
            "title": row.title or default_title(row.goal),
            "goal": row.goal,
            "status": row.status,
            "current_step": row.current_step,
            "cost_estimate_cny": row.cost_estimate_cny,
            "pending_gates": [{"gate_id": gate.id, "type": gate.type,
                               "param_id": gate.param_id} for gate in gates],
            "last_error": row.last_error,
            "updated_at": _iso(row.updated_at),
        }


def rename_mission(task_id: str, title: str) -> dict:
    title = (title or "").strip()[:120]
    if not title:
        raise MissionError("任务名称不能为空")
    with new_session() as session:
        row = session.get(Mission, task_id)
        if row is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        row.title = title
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"task_id": row.id, "title": row.title}
