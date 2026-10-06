"""参数接口（docs/07 §A6~A8）。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import api_error, require_token
from app.db import new_session
from app.models import AuditLog, CalculationRecord, DesignParameter, Mission, ReviewGate, ValidationResult
from app.orchestrator import engine

router = APIRouter(tags=["Parameters"])


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


@router.post("/missions/{mission_id}/parameters/{param_id}/review")
async def review_parameter(mission_id: str, param_id: str, body: ReviewBody,
                           _: None = Depends(require_token)) -> dict:
    resume_needed = False
    with new_session() as session:
        _ensure_mission(session, mission_id)
        row = session.get(DesignParameter, (param_id, mission_id))
        if row is None:
            api_error(404, "PARAM_NOT_FOUND", "参数不存在", {"param_id": param_id})
        if row.status not in ("needs_review", "proposed"):
            api_error(409, "STATE_CONFLICT", "当前参数状态不允许评审", {"status": row.status})
        if body.action == "reject" and not body.comment:
            api_error(400, "SCHEMA_INVALID", "reject 必须提供 comment", {"field": "comment"})

        before = {"status": row.status, "value": row.value}
        if body.action == "accept":
            if body.edited_value is not None:
                row.value = body.edited_value
                row.version += 1
            row.status = "verified"
        else:
            row.status = "rejected"

        gate = (session.query(ReviewGate)
                .filter(ReviewGate.mission_id == mission_id, ReviewGate.action.is_(None))
                .order_by(ReviewGate.ts).first())
        gate_info = None
        if gate is not None:
            gate.action = body.action
            gate.reviewer = body.reviewer
            gate.comment = body.comment
            gate.ts = datetime.now(timezone.utc)
            gate_info = {"gate_id": gate.id, "action": gate.action,
                         "reviewer": gate.reviewer, "ts": gate.ts.isoformat()}

        session.add(AuditLog(
            entity="design_parameter", entity_id=row.id, field="status",
            before=before, after={"status": row.status, "value": row.value},
            who=body.reviewer, why=body.comment or f"A8 {body.action}",
        ))
        session.flush()  # autoflush=False：先落库再做剩余门禁统计
        remaining = (session.query(ReviewGate)
                     .filter(ReviewGate.mission_id == mission_id, ReviewGate.action.is_(None))
                     .count())
        resume_needed = remaining == 0
        result = {"param_id": row.id, "status": row.status, "gate": gate_info,
                  "revalidation": {"queued": resume_needed, "scope": f"param:{row.id}"}}
        session.commit()

    if resume_needed:
        asyncio.create_task(engine.continue_mission(mission_id))
    return result
