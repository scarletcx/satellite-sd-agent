"""S7 冲突消解建议（LLM 步，骨架实现：由校验结论生成方向性建议）。

约束：只给方向，不得输出未经计算的新数值（docs/05 §S7）。
"""
from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import ValidationResult


def _load_block_findings(mission_id: str) -> list[dict]:
    with new_session() as session:
        rows = session.scalars(
            select(ValidationResult).where(
                ValidationResult.mission_id == mission_id,
                ValidationResult.status == "block",
            )
        ).all()
    return [{"rule_id": r.rule_id, "status": r.status, "param_id": r.param_id,
             "message": r.message} for r in rows]


def run(ctx: dict) -> dict:
    findings = ctx.get("findings") or _load_block_findings(ctx["task_id"])
    suggestions = [
        {
            "param_id": f.get("param_id"),
            "rule": f["rule_id"],
            "direction": "复核输入假设或放宽对应约束后重新校验",
            "rationale": f["message"],
        }
        for f in findings if f["status"] == "block"
    ]
    ctx["suggestions"] = suggestions
    return {"type": "llm", "output_ref": "suggestions", "count": len(suggestions)}
