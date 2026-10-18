"""评审服务：参数/假设的接受、驳回、批量确认与门禁恢复（API 与聊天工具复用）。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pydantic import ValidationError

from app.db import new_session
from app.models import Assumption, AuditLog, DesignParameter, Mission, ReviewGate
from app.orchestrator import engine
from app.orchestrator.ids import next_assumption_id
from app.orchestrator.schedule import schedule
from app.steps.common import unconfirmed_total
from app.tools.calc.adcs import AdcsInput
from app.tools.calc.budgets import DataInput, MassInput, PowerInput
from app.tools.calc.eps import EpsInput
from app.tools.calc.link import LinkInput
from app.tools.calc.orbit import OrbitInput

CONFIRMABLE_STATUSES = ("draft", "needs_review", "proposed", "rejected")
GROUP_INPUT_MODELS = {
    "orbit": OrbitInput,
    "mass": MassInput,
    "power": PowerInput,
    "eps": EpsInput,
    "data": DataInput,
    "link": LinkInput,
}


class ReviewError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


def _validate_group_payload(group: str, payload: dict) -> dict:
    model = GROUP_INPUT_MODELS.get(group)
    if model is None:
        raise ReviewError("SCHEMA_INVALID", f"未知的设计输入分组：{group}")
    try:
        return model(**payload).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ())) or "?"
        raise ReviewError("SCHEMA_INVALID",
                          f"输入参数不合法：{location}（{first.get('msg', '')}）") from exc


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


def _fail_mission(session, mission_id: str, code: str, message: str) -> None:
    mission = session.get(Mission, mission_id)
    if mission is not None:
        mission.status = "failed"
        mission.last_error = {"code": code, "message": message}


def _apply_parameter(session, mission_id: str, param_id: str, action: str, reviewer: str,
                     comment: str | None, edited_value: float | None,
                     edited_payload: dict | None) -> dict:
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
                raise ReviewError("SCHEMA_INVALID", "分组设计输入请修改 JSON 参数（edited_payload）",
                                  details={"field": "edited_value"})
            if edited_payload is not None:
                group = row.id.split(".", 1)[1]
                row.payload = _validate_group_payload(group, edited_payload)
            assumption_id = next_assumption_id(session, mission_id)
            session.add(Assumption(
                id=assumption_id, mission_id=mission_id,
                content=f"设计输入「{row.name}」经 {reviewer} 确认采用 S4 草案值",
                basis=comment or "S4 模型建议；工程师确认无异议",
                related_params=[row.id], status="confirmed",
                registered_by=f"review:{reviewer}",
                confirmed_by=reviewer, confirmed_at=datetime.now(timezone.utc),
            ))
            session.flush()  # autoflush=False：让后续 next_assumption_id 看到新记录
            row.status = "assumed"
            row.source_type = "assumption"
            row.source_ref = assumption_id
        else:
            if edited_value is not None:
                row.value = edited_value
                row.version += 1
            row.status = "verified"
            row.waived = True  # 人工接受：后续重跑校验时若仍超限，降级为 warn
    else:
        row.status = "rejected"

    session.add(AuditLog(
        entity="design_parameter", entity_id=row.id, field="status",
        before=before, after={"status": row.status, "value": row.value},
        who=reviewer, why=comment or f"A8 {action}",
    ))
    return {"param_id": row.id, "status": row.status, "is_group": is_group_draft}


def _apply_assumption(session, mission_id: str, assumption_id: str, action: str,
                      reviewer: str, comment: str | None) -> dict:
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
    return {"assumption_id": row.id, "status": row.status}


def _finish(session, mission_id: str, reviewer: str, comment: str | None,
            action: str, result: dict) -> dict:
    """统一收尾：驳回 → 任务失败并关闭门禁；全部确认 → 关门禁并恢复。"""
    session.flush()
    if action == "reject":
        _fail_mission(session, mission_id, "REVIEW_REJECTED",
                      "评审被驳回：请修改参数或任务书后重新执行/校验")
        gate_info = _close_pending_gates(session, mission_id, reviewer, comment, action)
        result.update({"gate": gate_info, "mission_failed": True,
                       "revalidation": {"queued": False}})
        return result

    remaining = unconfirmed_total(session, mission_id)
    gate_info = None
    resume_needed = False
    if remaining == 0:
        gate_info = _close_pending_gates(session, mission_id, reviewer, comment, action)
        resume_needed = gate_info is not None
    result.update({"gate": gate_info, "remaining_confirmations": remaining,
                   "revalidation": {"queued": resume_needed}})
    result["_resume"] = resume_needed
    return result


def review_parameter(mission_id: str, param_id: str, action: str, reviewer: str,
                     comment: str | None = None, edited_value: float | None = None,
                     edited_payload: dict | None = None) -> dict:
    with new_session() as session:
        result = _apply_parameter(session, mission_id, param_id, action, reviewer,
                                  comment, edited_value, edited_payload)
        result = _finish(session, mission_id, reviewer, comment, action, result)
        resume = result.pop("_resume", False)
        session.commit()
    if resume:
        schedule(lambda: engine.continue_mission(mission_id))
    return result


def review_assumption(mission_id: str, assumption_id: str, action: str,
                      reviewer: str, comment: str | None = None) -> dict:
    with new_session() as session:
        result = _apply_assumption(session, mission_id, assumption_id, action, reviewer, comment)
        result = _finish(session, mission_id, reviewer, comment, action, result)
        resume = result.pop("_resume", False)
        session.commit()
    if resume:
        schedule(lambda: engine.continue_mission(mission_id))
    return result


def _pending_needs_review(mission_id: str) -> list[str]:
    with new_session() as session:
        return [row[0] for row in session.query(DesignParameter.id).filter(
            DesignParameter.mission_id == mission_id,
            DesignParameter.status.in_(("draft", "needs_review", "rejected")),
        ).all()]


def _mission_status(mission_id: str) -> str | None:
    with new_session() as session:
        mission = session.get(Mission, mission_id)
        return mission.status if mission else None


def accept_all(mission_id: str, reviewer: str = "engineer",
               comment: str | None = "一键确认全部待处理项") -> dict:
    """一键确认：草案输入（默认值）、未确认假设、待评审参数（含超限豁免）。

    校验是确定性的、很快：如果放行后立刻产生新的校验门禁（例如链路余量不足），
    会在有限轮次内继续按“人工接受（豁免）”处理，避免用户反复点击。
    """
    accepted_params = accepted_assumptions = 0
    rounds = 0
    gate_info = None
    resume = False

    for _ in range(3):
        rounds += 1
        with new_session() as session:
            params = (session.query(DesignParameter)
                      .filter(DesignParameter.mission_id == mission_id,
                              DesignParameter.status.in_(("draft", "needs_review", "rejected")))
                      .order_by(DesignParameter.id).all())
            for row in params:
                _apply_parameter(session, mission_id, row.id, "accept", reviewer,
                                 comment, None, None)
                accepted_params += 1

            assumptions = (session.query(Assumption)
                           .filter(Assumption.mission_id == mission_id,
                                   Assumption.status == "open").all())
            for row in assumptions:
                _apply_assumption(session, mission_id, row.id, "accept", reviewer, comment)
                accepted_assumptions += 1

            session.flush()
            remaining = unconfirmed_total(session, mission_id)
            if remaining == 0:
                gate_info = _close_pending_gates(session, mission_id, reviewer, comment, "accept")
                resume = gate_info is not None
            session.commit()

        if not resume:
            break

        import time

        schedule(lambda: engine.continue_mission(mission_id))
        # 等待确定性校验跑完：等到「有新的待评审参数的门禁」或终态
        deadline = time.time() + 6.0
        status = _mission_status(mission_id)
        pending: list[str] = []
        while time.time() < deadline:
            status = _mission_status(mission_id)
            pending = _pending_needs_review(mission_id)
            if status == "awaiting_gate" and pending:
                break
            if status in ("succeeded", "failed"):
                pending = []
                break
            time.sleep(0.2)
        if status != "awaiting_gate" or not pending:
            break
        resume = False

    with new_session() as session:
        remaining = unconfirmed_total(session, mission_id)
    return {
        "mission_id": mission_id,
        "accepted_parameters": accepted_params,
        "accepted_assumptions": accepted_assumptions,
        "remaining_confirmations": remaining,
        "rounds": rounds,
        "gate": gate_info,
        "revalidation": {"queued": resume},
    }
