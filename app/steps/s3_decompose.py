"""S3 方案分解（LLM 步）；结果落盘 system-design.json，供断点恢复与回放。"""
from __future__ import annotations

import json

from app.providers import chat_json
from app.tracing import task_dir


def run(ctx: dict) -> dict:
    system_design = chat_json("S3", {
        "task_id": ctx["task_id"],
        "mission_request": ctx["mission_request"],
        "citations": ctx.get("citations", []),
    })
    ctx["system_design"] = system_design
    (task_dir(ctx["task_id"]) / "system-design.json").write_text(
        json.dumps(system_design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"type": "llm", "output_ref": "system_design"}
