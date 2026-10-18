"""评审服务：参数/假设的接受、驳回与门禁恢复；供 API 与聊天工具复用。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.db import new_session
from app.models import Assumption, AuditLog, DesignParameter, ReviewGate
from app.orchestrator import engine
from app.orchestrator.ids import next_assumption_id
from app.steps.common import unconfirmed_total

CONFIRMABLE_STATUSES = ("draft", "needs_review", "proposed", "rejected")


class ReviewError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


def _close_pending_gates(session, mission_id: str, reviewer: str, comment: str | None,
                         action: str) -> dict | None:
    gates = (session.query(ReviewGate)
             .filter(ReviewGate.mission_id == mission_id, ReviewGate.action.is_(None))
             .order_by(ReviewGate.ts).all())
    info = None
    for gate in gates:
        gate.action = action
        gate.reviewer = reviewer
        gate.comment = comment
        gate.ts = datetime.now(timezone.utc)
        if info is None:
            info = {"gate_id": gate.id, "action": gate.action,
                    "reviewer": gate.reviewer, "ts": gate.ts.isoformat()}
    return info


def review_parameter(mission_id: str, param_id: str, action: str, reviewer: str,
                     comment: str | None = None,
                     edited_value: float | None = None) -> dict:
    resume_needed = False
    with new_session() as session:
        row = session.get(DesignParameter, (param_id, mission_id))
        if row is None:
            raise ReviewError("PARAM_NOT_FOUND", "参数不存在", status=404,
                              details={"param_id": param_id})
        if row.status not in CONFIRMABLE_STATUSES:
            raise ReviewError("STATE_CONFLICT", "当前参数状态不允许评审",
                              status=409, details={"status": row.status})
        if action == "reject" and not comment:
            raise ReviewError("SCHEMA_INVALID", "reject 必须提供 comment",
                              details={"field": "comment"})

        is_group_draft = row.id.startswith("input.")
        before = {"status": row.status, "value": row.value}
        if action == "accept":
            if is_group_draft:
                if edited_value is not None:
                    raise ReviewError("SCHEMA_INVALID",
                                      "分组草案输入不支持直接改值（请驳回后调整任务书）",
                                      details={"field": "edited_value"})
                assumption_id = next_assumption_id(session, mission_id)
                session.add(Assumption(
                    id=assumption_id, mission_id=mission_id,
                    content=f"设计输入「{row.name}」经 {reviewer} 确认采用 S4 草案值",
                    basis=comment or "S4 模型建议；工程师确认无异议",
                    related_params=[row.id], status="confirmed",
                    registered_by=f"review:{reviewer}",
                    confirmed_by=reviewer, confirmed_at=datetime.now(timezone.utc),
                ))
                row.status = "assumed"
                row.source_type = "assumption"
                row.source_ref = assumption_id
            else:
                if edited_value is not None:
                    row.value = edited_value
                    row.version += 1
                row.status = "verified"
        else:
            row.status = "rejected"

        session.add(AuditLog(
            entity="design_parameter", entity_id=row.id, field="status",
            before=before, after={"status": row.status, "value": row.value},
            who=reviewer, why=comment or f"A8 {action}",
        ))
        session.flush()

        remaining = unconfirmed_total(session, mission_id)
        gate_info = None
        if remaining == 0:
            gate_info = _close_pending_gates(session, mission_id, reviewer, comment, action)
            resume_needed = gate_info is not None
        result = {"param_id": row.id, "status": row.status, "gate": gate_info,
                  "remaining_confirmations": remaining,
                  "revalidation": {"queued": resume_needed, "scope": f"param:{row.id}"}}
        session.commit()

    if resume_needed:
        asyncio.create_task(engine.continue_mission(mission_id))
    return result


def review_assumption(mission_id: str, assumption_id: str, action: str,
                      reviewer: str, comment: str | None = None) -> dict:
    resume_needed = False
    with new_session() as session:
        row = session.get(Assumption, (assumption_id, mission_id))
        if row is None:
            raise ReviewError("ASSUMPTION_NOT_FOUND", "假设不存在", status=404,
                              details={"assumption_id": assumption_id})
        if row.status != "open":
            raise ReviewError("STATE_CONFLICT", "当前假设状态不允许评审",
                              status=409, details={"status": row.status})
        if action == "reject" and not comment:
            raise ReviewError("SCHEMA_INVALID", "reject 必须提供 comment",
                              details={"field": "comment"})

        before = {"status": row.status}
        row.status = "confirmed" if action == "accept" else "rejected"
        row.confirmed_by = reviewer
        row.confirmed_at = datetime.now(timezone.utc)
        session.add(AuditLog(
            entity="assumption", entity_id=row.id, field="status",
            before=before, after={"status": row.status},
            who=reviewer, why=comment or f"A14 {action}",
        ))
        session.flush()

        remaining = unconfirmed_total(session, mission_id)
        gate_info = None
        if remaining == 0:
            gate_info = _close_pending_gates(session, mission_id, reviewer, comment, action)
            resume_needed = gate_info is not None
        result = {"assumption_id": row.id, "status": row.status, "gate": gate_info,
                  "remaining_confirmations": remaining}
        session.commit()

    if resume_needed:
        asyncio.create_task(engine.continue_mission(mission_id))
    return result
