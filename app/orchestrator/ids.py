"""ID 生成（规则见 docs/03 §8）。演示级实现：按计数递增。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CalculationRecord, Mission, ReviewGate, ValidationResult


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _count(session: Session, model, mission_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(model).where(model.mission_id == mission_id)
    ) or 0


def next_mission_id(session: Session) -> str:
    count = session.scalar(
        select(func.count()).select_from(Mission).where(Mission.id.like(f"t-{_today()}-%"))
    ) or 0
    return f"t-{_today()}-{count + 1:03d}"


def next_calc_ids(session: Session, mission_id: str, k: int) -> list[str]:
    """计算记录 ID 为「当日全局序号」（格式 calc-YYYYMMDD-NNNN，跨任务唯一）。"""
    base = session.scalar(
        select(func.count()).select_from(CalculationRecord)
        .where(CalculationRecord.id.like(f"calc-{_today()}-%"))
    ) or 0
    return [f"calc-{_today()}-{base + i + 1:04d}" for i in range(k)]


def next_vr_ids(session: Session, mission_id: str, k: int) -> list[str]:
    base = _count(session, ValidationResult, mission_id)
    return [f"vr-{base + i + 1:04d}" for i in range(k)]


def next_gate_id(session: Session, mission_id: str) -> str:
    base = _count(session, ReviewGate, mission_id)
    return f"g-{base + 1:03d}"
