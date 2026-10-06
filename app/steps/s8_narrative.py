"""S8 叙述撰写（LLM 步）：数字占位符化、引用白名单（docs/05 §S8）。

上下文包含已验证参数与引用清单；输出键 1_overview / 4_mass / 5_power / 6_data / 11_risk。
"""
from __future__ import annotations

import json

from app.db import new_session
from app.providers import chat_json
from app.steps.common import load_params
from app.tracing import task_dir


def _load_citations(task_id: str) -> list[dict]:
    path = task_dir(task_id) / "citations.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run(ctx: dict) -> dict:
    mission_request = ctx.get("mission_request") or {
        "goal": ctx["goal"],
        "constraints": ctx["constraints"],
        "language": "zh",
    }
    with new_session() as session:
        params = load_params(session, ctx["task_id"])
    citations = ctx.get("citations") or _load_citations(ctx["task_id"])

    payload = chat_json("S8", {
        "task_id": ctx["task_id"],
        "mission_request": mission_request,
        "params": [{"id": p["id"], "value": p["value"], "unit": p["unit"]} for p in params],
        "available_param_ids": [p["id"] for p in params],
        "citations": [{"id": c.get("id"), "title": c.get("title")} for c in citations],
    })

    narrative = payload.get("sections", payload) if isinstance(payload, dict) else {}
    ctx["narrative"] = narrative
    return {"type": "llm", "output_ref": "narrative"}
