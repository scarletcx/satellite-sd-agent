"""参数接口（docs/07 §A6~A8）与假设台账接口（A14）。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import api_error, require_token
from app.db import new_session
from app.models import (
    Assumption,
    AuditLog,
    CalculationRecord,
    DesignParameter,
    Mission,
    ReviewGate,
    ValidationResult,
)
from app.orchestrator import engine
from app.orchestrator.ids import next_assumption_id
from app.steps.common import unconfirmed_total

router = APIRouter(tags=["Parameters"])

CONFIRMABLE_STATUSES = ("draft", "needs_review", "proposed", "rejected")


def _ensure_mission(session, mission_id: str) -> Mission:
    mission = session.get(Mission, mission_id)
    if mission is None:
        api_error(404, "MISSION_NOT_FOUND", "任务不存在", {"task_id": mission_id})
    return mission


def _latest_validation_map(session, mission_id: str) -> dict[str, str]:
    rows = (session.query(ValidationResult)
            .filter(ValidationResult.mission_id == mission_id)
            .order_by(ValidationResult.created_at.asc())
            .all())
    mapping: dict[str, str] = {}
    for row in rows:
        if row.param_id:
            mapping[row.param_id] = row.status
    return mapping


# ---------------------------------------------------------------- A6 列表


@router.get("/missions/{mission_id}/parameters")
def list_parameters(
    mission_id: str,
    status: str | None = Query(default=None),
    module: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    _: None = Depends(require_token),
) -> dict:
    with new_session() as session:
        _ensure_mission(session, mission_id)
        query = session.query(DesignParameter).filter(DesignParameter.mission_id == mission_id)
        if status:
            query = query.filter(DesignParameter.status == status)
        if module:
            query = query.filter(DesignParameter.id.like(f"{module}.%"))
        total = query.count()
        rows = (query.order_by(DesignParameter.id)
                .offset((page - 1) * page_size).limit(page_size).all())
        validation_map = _latest_validation_map(session, mission_id)
        items = [{
            "id": r.id, "name": r.name, "unit": r.unit, "value": r.value,
            "status": r.status, "source_type": r.source_type, "margin": r.margin,
            "validation_status": validation_map.get(r.id),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        } for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------- A7 详情


@router.get("/missions/{mission_id}/parameters/{param_id}")
def get_parameter(mission_id: str, param_id: str, _: None = Depends(require_token)) -> dict:
    with new_session() as session:
        _ensure_mission(session, mission_id)
        row = session.get(DesignParameter, (param_id, mission_id))
        if row is None:
            api_error(404, "PARAM_NOT_FOUND", "参数不存在", {"param_id": param_id})

        provenance = None
        if row.source_type == "calc":
            record = session.get(CalculationRecord, row.source_ref)
            if record is not None:
                provenance = {
                    "type": "calculation",
                    "record": {
                        "id": record.id, "tool": record.tool,
                        "formula_version": record.formula_version,
                        "inputs": record.inputs, "outputs": record.outputs,
                        "code_commit": record.code_commit,
                        "created_at": record.created_at.isoformat() if record.created_at else None,
                    },
                }
        elif row.source_type == "assumption":
            provenance = {"type": "assumption", "record": {"id": row.source_ref}}
        else:
            provenance = {"type": row.source_type, "record": {"id": row.source_ref}}

        validations = (session.query(ValidationResult)
                       .filter(ValidationResult.mission_id == mission_id,
                               ValidationResult.param_id == param_id)
                       .order_by(ValidationResult.created_at.desc()).limit(10).all())

        return {
            "id": row.id, "name": row.name, "value": row.value, "unit": row.unit,
            "source_type": row.source_type, "source_ref": row.source_ref,
            "margin": row.margin, "confidence": row.confidence, "status": row.status,
            "version": row.version, "parent": row.parent,
            "derived_from": list(row.derived_from or []),
            "provenance": provenance,
            "validations": [{"rule_id": v.rule_id, "status": v.status,
                             "created_at": v.created_at.isoformat() if v.created_at else None}
                            for v in validations],
        }


# ------------------------------------------------------------ A8 评审门禁


class ReviewBody(BaseModel):
    action: Literal["accept", "reject"]
    reviewer: str
    comment: str | None = None
    edited_value: float | None = None


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


@router.post("/missions/{mission_id}/parameters/{param_id}/review")
async def review_parameter(mission_id: str, param_id: str, body: ReviewBody,
                           _: None = Depends(require_token)) -> dict:
    resume_needed = False
    with new_session() as session:
        _ensure_mission(session, mission_id)
        row = session.get(DesignParameter, (param_id, mission_id))
        if row is None:
            api_error(404, "PARAM_NOT_FOUND", "参数不存在", {"param_id": param_id})
        if row.status not in CONFIRMABLE_STATUSES:
            api_error(409, "STATE_CONFLICT", "当前参数状态不允许评审", {"status": row.status})
        if body.action == "reject" and not body.comment:
            api_error(400, "SCHEMA_INVALID", "reject 必须提供 comment", {"field": "comment"})

        is_group_draft = row.id.startswith("input.")
        before = {"status": row.status, "value": row.value}
        if body.action == "accept":
            if is_group_draft:
                if body.edited_value is not None:
                    api_error(400, "SCHEMA_INVALID",
                              "分组草案输入不支持直接改值（请调整任务书后重跑，或驳回并修订）",
                              {"field": "edited_value"})
                assumption_id = next_assumption_id(session, mission_id)
                session.add(Assumption(
                    id=assumption_id, mission_id=mission_id,
                    content=f"设计输入「{row.name}」经 {body.reviewer} 确认采用 S4 草案值",
                    basis=body.comment or "S4 模型建议；工程师确认无异议",
                    related_params=[row.id], status="confirmed",
                    registered_by=f"review:{body.reviewer}",
                    confirmed_by=body.reviewer, confirmed_at=datetime.now(timezone.utc),
                ))
                row.status = "assumed"
                row.source_type = "assumption"
                row.source_ref = assumption_id
            else:
                if body.edited_value is not None:
                    row.value = body.edited_value
                    row.version += 1
                row.status = "verified"
        else:
            row.status = "rejected"

        session.add(AuditLog(
            entity="design_parameter", entity_id=row.id, field="status",
            before=before, after={"status": row.status, "value": row.value},
            who=body.reviewer, why=body.comment or f"A8 {body.action}",
        ))
        session.flush()  # autoflush=False：先落库再统计剩余确认项

        remaining = unconfirmed_total(session, mission_id)
        gate_info = None
        if remaining == 0:
            gate_info = _close_pending_gates(session, mission_id, body.reviewer,
                                             body.comment, body.action)
            resume_needed = gate_info is not None
        result = {"param_id": row.id, "status": row.status, "gate": gate_info,
                  "remaining_confirmations": remaining,
                  "revalidation": {"queued": resume_needed, "scope": f"param:{row.id}"}}
        session.commit()

    if resume_needed:
        asyncio.create_task(engine.continue_mission(mission_id))
    return result


# --------------------------------------------------------- A14 假设台账


def _assumption_item(row: Assumption) -> dict:
    return {
        "id": row.id, "content": row.content, "basis": row.basis,
        "related_params": list(row.related_params or []), "status": row.status,
        "registered_by": row.registered_by, "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


@router.get("/missions/{mission_id}/assumptions")
def list_assumptions(mission_id: str, status: str | None = Query(default=None),
                     _: None = Depends(require_token)) -> dict:
    with new_session() as session:
        _ensure_mission(session, mission_id)
        query = session.query(Assumption).filter(Assumption.mission_id == mission_id)
        if status:
            query = query.filter(Assumption.status == status)
        rows = query.order_by(Assumption.id).all()
        items = [_assumption_item(row) for row in rows]
    return {"items": items, "total": len(items)}


class AssumptionReviewBody(BaseModel):
    action: Literal["accept", "reject"]
    reviewer: str
    comment: str | None = None


@router.post("/missions/{mission_id}/assumptions/{assumption_id}/review")
async def review_assumption(mission_id: str, assumption_id: str, body: AssumptionReviewBody,
                            _: None = Depends(require_token)) -> dict:
    resume_needed = False
    with new_session() as session:
        _ensure_mission(session, mission_id)
        row = session.get(Assumption, (assumption_id, mission_id))
        if row is None:
            api_error(404, "ASSUMPTION_NOT_FOUND", "假设不存在", {"assumption_id": assumption_id})
        if row.status != "open":
            api_error(409, "STATE_CONFLICT", "当前假设状态不允许评审", {"status": row.status})
        if body.action == "reject" and not body.comment:
            api_error(400, "SCHEMA_INVALID", "reject 必须提供 comment", {"field": "comment"})

        before = {"status": row.status}
        row.status = "confirmed" if body.action == "accept" else "rejected"
        row.confirmed_by = body.reviewer
        row.confirmed_at = datetime.now(timezone.utc)
        session.add(AuditLog(
            entity="assumption", entity_id=row.id, field="status",
            before=before, after={"status": row.status},
            who=body.reviewer, why=body.comment or f"A14 {body.action}",
        ))
        session.flush()

        remaining = unconfirmed_total(session, mission_id)
        gate_info = None
        if remaining == 0:
            gate_info = _close_pending_gates(session, mission_id, body.reviewer,
                                             body.comment, body.action)
            resume_needed = gate_info is not None
        result = {"assumption_id": row.id, "status": row.status, "gate": gate_info,
                  "remaining_confirmations": remaining}
        session.commit()

    if resume_needed:
        asyncio.create_task(engine.continue_mission(mission_id))
    return result
