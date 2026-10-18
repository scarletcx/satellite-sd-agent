"""S3 方案分解（LLM 步）；结果落盘 system-design.json，供断点恢复与回放。"""
from __future__ import annotations

import json

from app.providers import chat_json
from app.tracing import task_dir


def _normalize_envelope(system_design: dict) -> None:
    """模型可能给出 null/字符串尺寸；只保留可解析为数字的包络值，避免下游计算崩溃。"""
    config = system_design.get("configuration")
    if not isinstance(config, dict):
        return
    envelope = config.get("envelope_mm")
    if not isinstance(envelope, dict):
        return
    clean: dict = {}
    for axis, value in envelope.items():
        try:
            clean[axis] = float(value)
        except (TypeError, ValueError):
            continue
    if clean:
        config["envelope_mm"] = clean
    else:
        config.pop("envelope_mm", None)


def run(ctx: dict) -> dict:
    system_design = chat_json("S3", {
        "task_id": ctx["task_id"],
        "mission_request": ctx["mission_request"],
        "citations": ctx.get("citations", []),
    })
    _normalize_envelope(system_design)
    ctx["system_design"] = system_design
    (task_dir(ctx["task_id"]) / "system-design.json").write_text(
        json.dumps(system_design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"type": "llm", "output_ref": "system_design"}
