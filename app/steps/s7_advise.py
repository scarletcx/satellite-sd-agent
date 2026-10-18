"""S7 冲突消解建议（LLM 步）：基于 block 问题生成方向性建议。

硬约束（docs/05 §S7）：只给方向，不得输出未经计算的新数值。
输出中的数字必须能在「IR 参数 / 任务约束 / 校验问题原文」中找到（白名单校验）；
不通过则带错误重试 ≤2 次，仍失败回退到规则模板建议（离线可用）。
"""
from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import Mission, ValidationResult
from app.providers import chat_json
from app.providers.base import ProviderError
from app.steps.common import load_params, untraceable_numbers
from app.tools.doc.check import numbers_in_texts

_TEMPLATE_DIRECTIONS = {
    "V4": "复核任务书约束或做降额设计：从分系统分解中寻找减重/降耗空间",
    "V3": "复核预算闭合：检查输入假设与分系统数据是否自洽，必要时补充工况假设",
    "V2": "复核计算记录与输入快照：确认是否存在手工修改或版本错配",
    "V1": "补齐出处：为缺失来源的数字补充计算记录或显式假设，并重新评审",
    "V5": "与历史基线偏差较大：复核经验假设与任务书指标的可实现性",
    "V6": "结论对假设敏感：收紧关键假设或增加设计余量后再评估",
}


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


def _template_suggestions(blocks: list[dict]) -> list[dict]:
    return [
        {
            "param_id": item.get("param_id"),
            "rule_id": item.get("rule_id"),
            "direction": _TEMPLATE_DIRECTIONS.get(item.get("rule_id"), "复核该项的输入假设与约束条件"),
            "rationale": item.get("message", ""),
        }
        for item in blocks
    ]


def run(ctx: dict) -> dict:
    mission_id = ctx["task_id"]
    findings = ctx.get("findings") or _load_block_findings(mission_id)
    blocks = [item for item in findings if item.get("status") == "block"]
    if not blocks:
        ctx["suggestions"] = []
        return {"type": "llm", "output_ref": "suggestions", "count": 0, "source": "none"}

    with new_session() as session:
        mission = session.get(Mission, mission_id)
        constraints = dict(mission.constraints or {}) if mission else {}
        params = load_params(session, mission_id)

    allowed = [param["value"] for param in params]
    allowed += [float(value) for value in constraints.values()
                if isinstance(value, (int, float)) and not isinstance(value, bool)]
    allowed += numbers_in_texts([f"{item.get('message', '')} {item.get('param_id') or ''}"
                                 for item in blocks])

    suggestions = None
    retry_hint = ""
    for _ in range(3):
        try:
            payload = chat_json("S7", {
                "task_id": mission_id,
                "findings": blocks,
                "constraints": constraints,
                "retry_hint": retry_hint,
            })
        except ProviderError:
            break
        raw = [item for item in (payload.get("suggestions") or []) if isinstance(item, dict)]
        texts = [f"{item.get('direction', '')} {item.get('rationale', '')}" for item in raw]
        violations = untraceable_numbers(texts, allowed)
        if raw and not violations:
            suggestions = raw
            break
        retry_hint = (f"上次输出包含未经验证的数字：{sorted(set(violations))}；"
                      "请改写为不含这些数字的表述。" if violations else "上次输出为空，请按格式给出建议。")

    source = "llm"
    if suggestions is None:
        suggestions = _template_suggestions(blocks)
        source = "fallback"

    ctx["suggestions"] = suggestions
    return {"type": "llm", "output_ref": "suggestions",
            "count": len(suggestions), "source": source}
