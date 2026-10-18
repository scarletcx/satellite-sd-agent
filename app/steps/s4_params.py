"""S4 参数草案生成（LLM 步）→ 分组草案入 IR（status=draft）+ 假设台账登记。

设计输入以「分组草案」形式落库：id = input.<group>，payload 存整组计算输入。
未确认的草案不允许进入计算：编排层在 S4 之后设输入门禁，S5 读取时会再次强制校验。
工程师确认后，该组 source_type 变为 assumption 并关联一条已确认的假设记录。
"""
from __future__ import annotations

from app.db import new_session
from app.models import Assumption, DesignParameter
from app.providers import chat_json
from app.steps.common import INPUT_GROUPS

GROUP_LABELS = {
    "orbit": "轨道与覆盖",
    "mass": "质量预算",
    "power": "功耗预算",
    "eps": "太阳翼与电池",
    "data": "数据量预算",
    "link": "测控链路",
}


def run(ctx: dict) -> dict:
    payload = chat_json("S4", {
        "task_id": ctx["task_id"],
        "mission_request": ctx["mission_request"],
        "system_design": ctx.get("system_design", {}),
    })
    ctx["s4"] = payload

    with new_session() as session:
        for item in payload.get("assumptions", []):
            session.merge(Assumption(
                id=item["id"],
                mission_id=ctx["task_id"],
                content=item["content"],
                basis=item["basis"],
                related_params=item["related_params"],
                status="open",
                registered_by="system:S4",
            ))

        for group in INPUT_GROUPS:
            row = session.get(DesignParameter, (f"input.{group}", ctx["task_id"]))
            data = dict(payload.get(group) or {})
            if row is None:
                session.add(DesignParameter(
                    id=f"input.{group}", mission_id=ctx["task_id"],
                    name=f"设计输入：{GROUP_LABELS[group]}（S4 草案）",
                    value=0.0, unit="1",
                    source_type="model", source_ref="S4",
                    status="draft", confidence="low", parent="input",
                    payload=data,
                ))
            else:
                row.payload = data
                row.status = "draft"
                row.source_type = "model"
                row.source_ref = "S4"
                row.version += 1
        session.commit()

    return {"type": "llm", "output_ref": "s4_params",
            "assumptions": len(payload.get("assumptions", [])),
            "draft_groups": len(INPUT_GROUPS)}
