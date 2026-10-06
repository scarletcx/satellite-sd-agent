"""S1 任务书解析与澄清（LLM 步）。

解析后的归一化约束写回任务行：保证断点恢复（如门禁放行后从 S7 继续）时上下文一致。
"""
from __future__ import annotations

from app.db import new_session
from app.models import Mission
from app.providers import chat_json


def run(ctx: dict) -> dict:
    mission_request = chat_json("S1", {
        "task_id": ctx["task_id"],
        "goal": ctx["goal"],
        "constraints": ctx["constraints"],
    })
    ctx["mission_request"] = mission_request

    normalized = dict(mission_request.get("constraints", {}) or {})
    with new_session() as session:
        mission = session.get(Mission, ctx["task_id"])
        if mission is not None:
            mission.constraints = normalized
            session.commit()

    ctx["constraints"] = normalized
    return {"type": "llm", "output_ref": "mission_request"}
