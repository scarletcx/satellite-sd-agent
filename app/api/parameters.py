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
from app.services import reviews as review_service
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
            "payload": row.payload,
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
    edited_payload: dict | None = None  # 分组设计输入（JSON）修改


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
    with new_session() as session:
        _ensure_mission(session, mission_id)
    try:
        return review_service.review_parameter(
            mission_id, param_id, body.action, body.reviewer,
            body.comment, body.edited_value, body.edited_payload,
        )
    except review_service.ReviewError as exc:
        api_error(exc.status, exc.code, str(exc), exc.details)


@router.post("/missions/{mission_id}/reviews/accept-all")
async def accept_all_reviews(mission_id: str, body: AcceptAllBody | None = None,
                             _: None = Depends(require_token)) -> dict:
    """一键确认全部：草案输入（默认值）、未确认假设、待评审参数（含超限豁免）。"""
    with new_session() as session:
        _ensure_mission(session, mission_id)
    return review_service.accept_all(
        mission_id,
        reviewer=(body.reviewer if body else "engineer"),
        comment=(body.comment if body else None),
    )


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


class AcceptAllBody(BaseModel):
    reviewer: str = "engineer"
    comment: str | None = None


class AssumptionReviewBody(BaseModel):
    action: Literal["accept", "reject"]
    reviewer: str
    comment: str | None = None


@router.post("/missions/{mission_id}/assumptions/{assumption_id}/review")
async def review_assumption(mission_id: str, assumption_id: str, body: AssumptionReviewBody,
                            _: None = Depends(require_token)) -> dict:
    with new_session() as session:
        _ensure_mission(session, mission_id)
    try:
        return review_service.review_assumption(
            mission_id, assumption_id, body.action, body.reviewer, body.comment)
    except review_service.ReviewError as exc:
        api_error(exc.status, exc.code, str(exc), exc.details)
