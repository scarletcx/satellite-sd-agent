"""ID 生成（规则见 docs/03 §8）：按「当日/当任务已有最大序号 + 1」递增，删除后不复用，避免唯一键冲突。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CalculationRecord,
    ChatDocument,
    Mission,
    ReviewGate,
    SelectionCandidate,
    ValidationResult,
)


def _today() -> str:
    """本地日期（个人 agent：按用户时区生成任务/会话编号）。"""
    return datetime.now().astimezone().strftime("%Y%m%d")


def _next_index(ids: list[str], prefix: str) -> int:
    """取已有编号的最大序号 + 1（编号形如 <prefix><数字>）。"""
    best = 0
    offset = len(prefix)
    for value in ids:
        suffix = str(value)[offset:]
        if suffix.isdigit():
            best = max(best, int(suffix))
    return best + 1


def _scoped_ids(session: Session, model, mission_id: str, prefix: str) -> list[str]:
    return list(session.scalars(
        select(model.id).where(model.mission_id == mission_id, model.id.like(f"{prefix}%"))
    ).all())


def next_mission_id(session: Session) -> str:
    prefix = f"t-{_today()}-"
    ids = session.scalars(select(Mission.id).where(Mission.id.like(f"{prefix}%"))).all()
    return f"{prefix}{_next_index(list(ids), prefix):03d}"


def next_calc_ids(session: Session, mission_id: str, k: int) -> list[str]:
    """计算记录 ID 为「当日全局序号」（格式 calc-YYYYMMDD-NNNN，跨任务唯一）。"""
    prefix = f"calc-{_today()}-"
    ids = session.scalars(
        select(CalculationRecord.id).where(CalculationRecord.id.like(f"{prefix}%"))
    ).all()
    base = _next_index(list(ids), prefix)
    return [f"{prefix}{base + i:04d}" for i in range(k)]


def next_vr_ids(session: Session, mission_id: str, k: int) -> list[str]:
    base = _next_index(_scoped_ids(session, ValidationResult, mission_id, "vr-"), "vr-")
    return [f"vr-{base + i:04d}" for i in range(k)]


def next_gate_id(session: Session, mission_id: str) -> str:
    base = _next_index(_scoped_ids(session, ReviewGate, mission_id, "g-"), "g-")
    return f"g-{base:03d}"


def next_assumption_id(session: Session, mission_id: str) -> str:
    from app.models import Assumption

    base = _next_index(_scoped_ids(session, Assumption, mission_id, "asm-"), "asm-")
    return f"asm-{base:04d}"


def next_candidate_ids(session: Session, mission_id: str, k: int) -> list[str]:
    base = _next_index(_scoped_ids(session, SelectionCandidate, mission_id, "sc-"), "sc-")
    return [f"sc-{base + i:04d}" for i in range(k)]


def next_chat_session_id(session: Session) -> str:
    from app.models import ChatSession

    prefix = f"cs-{_today()}-"
    ids = session.scalars(select(ChatSession.id).where(ChatSession.id.like(f"{prefix}%"))).all()
    return f"{prefix}{_next_index(list(ids), prefix):03d}"


def next_chat_document_id(session: Session, session_id: str) -> str:
    prefix = "cd-"
    ids = session.scalars(
        select(ChatDocument.id).where(ChatDocument.session_id == session_id,
                                      ChatDocument.id.like(f"{prefix}%"))
    ).all()
    return f"{prefix}{_next_index(list(ids), prefix):04d}"
