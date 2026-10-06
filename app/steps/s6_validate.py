"""S6 一致性校验（确定性）：V1 / V3 / V4（骨架实现，规则见 app/validation/rules.py）。

出现 block → 冻结相关参数、生成门禁，由引擎挂起（status=awaiting_gate）。
"""
from __future__ import annotations

from app.db import new_session
from app.models import Assumption, CalculationRecord, DesignParameter, Mission, ReviewGate, ValidationResult
from app.orchestrator.ids import next_gate_id, next_vr_ids
from app.steps.common import load_params
from app.validation.rules import run_validation, summarize


def run(ctx: dict) -> dict:
    mission_id = ctx["task_id"]
    with new_session() as session:
        mission = session.get(Mission, mission_id)
        params = load_params(session, mission_id)
        refs = {
            "calc": {row.id for row in session.query(CalculationRecord)
                     .filter(CalculationRecord.mission_id == mission_id).all()},
            "assumption": {row.id for row in session.query(Assumption)
                           .filter(Assumption.mission_id == mission_id).all()},
        }
        records = [
            {"id": row.id, "tool": row.tool,
             "inputs": dict(row.inputs or {}), "outputs": dict(row.outputs or {})}
            for row in session.query(CalculationRecord)
            .filter(CalculationRecord.mission_id == mission_id).all()
        ]
        assumptions = [
            {"id": a.id, "status": a.status, "content": a.content}
            for a in session.query(Assumption).filter(Assumption.mission_id == mission_id).all()
        ]
        findings = run_validation(params, dict(mission.constraints or {}),
                                  refs=refs, assumptions=assumptions, records=records)

        for vid, f in zip(next_vr_ids(session, mission_id, len(findings)), findings):
            session.add(ValidationResult(
                id=vid, mission_id=mission_id, rule_id=f["rule_id"], status=f["status"],
                param_id=f["param_id"], message=f["message"], evidence=f["evidence"],
            ))

        blocked = [f for f in findings if f["status"] == "block"]
        if blocked:
            for f in blocked:
                if f["param_id"]:
                    row = session.get(DesignParameter, (f["param_id"], mission_id))
                    if row is not None:
                        row.status = "needs_review"
            session.add(ReviewGate(
                id=next_gate_id(session, mission_id), mission_id=mission_id,
                type="discrepancy_resolve", param_id=blocked[0]["param_id"],
                action=None, reviewer=None, comment=None,
            ))
        else:
            for row in session.query(DesignParameter).filter_by(mission_id=mission_id).all():
                if row.source_type == "calc" and row.status == "proposed":
                    row.status = "verified"
        session.commit()

    ctx["findings"] = findings
    ctx["blocked"] = bool(blocked)
    return {"type": "validation", "validation_summary": summarize(findings),
            "blocked": bool(blocked)}
