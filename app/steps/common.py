"""步骤公共工具：参数 upsert 与读取。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DesignParameter


def upsert_parameter(
    session: Session,
    mission_id: str,
    *,
    id: str,
    name: str,
    value: float,
    unit: str,
    source_type: str,
    source_ref: str,
    margin: float | None = None,
    parent: str | None = None,
    confidence: str = "high",
    status: str = "proposed",
    derived_from: list | None = None,
) -> DesignParameter:
    row = session.get(DesignParameter, (id, mission_id))
    if row is None:
        row = DesignParameter(
            id=id, mission_id=mission_id, name=name, value=value, unit=unit,
            source_type=source_type, source_ref=source_ref, margin=margin,
            parent=parent, confidence=confidence, status=status,
            derived_from=derived_from or [],
        )
        session.add(row)
    else:
        row.value = value
        row.source_type = source_type
        row.source_ref = source_ref
        row.margin = margin
        row.confidence = confidence
        row.version += 1
    return row


def load_params(session: Session, mission_id: str) -> list[dict]:
    rows = session.scalars(
        select(DesignParameter)
        .where(DesignParameter.mission_id == mission_id)
        .order_by(DesignParameter.id)
    ).all()
    return [
        {
            "id": r.id, "name": r.name, "value": r.value, "unit": r.unit,
            "source_type": r.source_type, "source_ref": r.source_ref,
            "status": r.status, "confidence": r.confidence, "margin": r.margin,
            "version": r.version, "parent": r.parent, "derived_from": list(r.derived_from or []),
        }
        for r in rows
    ]
