"""S4 参数草案生成（LLM 步，桩 Provider）→ 登记假设台账。"""
from __future__ import annotations

from app.db import new_session
from app.models import Assumption
from app.providers import chat_json


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
        session.commit()

    return {"type": "llm", "output_ref": "s4_params",
            "assumptions": len(payload.get("assumptions", []))}
