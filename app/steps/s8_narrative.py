"""S8 叙述撰写（LLM 步）：数字占位符化、引用白名单（docs/05 §S8）。

输出经代码级白名单校验：裸数字必须能在 IR / 约束 / 任务书找到，引用编号必须真实存在；
不通过则带错误重试 ≤2 次，仍不通过就按句剔除违规内容，保证「没有出处的数字不进文档」。
"""
from __future__ import annotations

import json
import re

from app.db import new_session
from app.steps.common import load_params, untraceable_numbers
from app.tracing import task_dir

_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}")
_CITATION_RE = re.compile(r"\bS\d+\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[。；;！!？?\n])")
_SAFE_TEXT = "（本节内容因模型输出未通过白名单校验而省略，相关数值见预算表与校验报告。）"


def _load_citations(task_id: str) -> list[dict]:
    path = task_dir(task_id) / "citations.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _issues(text: str, allowed: list[float], citation_ids: set[str]) -> list[str]:
    plain = _PLACEHOLDER_RE.sub(" ", text or "")
    issues = [f"未验证数字 {value:g}" for value in untraceable_numbers([plain], allowed)]
    issues += [f"引用不存在 {ref}" for ref in sorted(set(_CITATION_RE.findall(plain)))
               if ref not in citation_ids]
    return issues


def _sanitize(narrative: dict, allowed: list[float], citation_ids: set[str]) -> tuple[dict, int]:
    cleaned: dict[str, str] = {}
    dropped = 0
    for key, text in narrative.items():
        kept = []
        for sentence in _SENTENCE_SPLIT.split(str(text or "")):
            if not sentence.strip():
                continue
            if _issues(sentence, allowed, citation_ids):
                dropped += 1
                continue
            kept.append(sentence)
        cleaned[key] = "".join(kept).strip() or _SAFE_TEXT
    return cleaned, dropped


def run(ctx: dict) -> dict:
    mission_request = ctx.get("mission_request") or {
        "goal": ctx["goal"],
        "constraints": ctx["constraints"],
        "language": "zh",
    }
    from app.providers import chat_json  # 延迟导入，便于测试注入

    with new_session() as session:
        params = load_params(session, ctx["task_id"])
    citations = ctx.get("citations") or _load_citations(ctx["task_id"])
    citation_ids = {str(item.get("id")) for item in citations if item.get("id")}

    constraints = (mission_request or {}).get("constraints") or {}
    allowed = [param["value"] for param in params]
    allowed += [float(value) for value in constraints.values()
                if isinstance(value, (int, float)) and not isinstance(value, bool)]
    allowed += [float(token) for token in re.findall(r"\d+(?:\.\d+)?",
                                                     json.dumps(mission_request, ensure_ascii=False))]

    narrative: dict | None = None
    candidate: dict = {}
    retry_hint = ""
    attempts = 0
    for attempt in range(3):
        attempts = attempt + 1
        payload = chat_json("S8", {
            "task_id": ctx["task_id"],
            "mission_request": mission_request,
            "params": [{"id": p["id"], "value": p["value"], "unit": p["unit"]} for p in params],
            "available_param_ids": [p["id"] for p in params],
            "citations": [{"id": c.get("id"), "title": c.get("title")} for c in citations],
            "retry_hint": retry_hint,
        })
        candidate = payload.get("sections", payload) if isinstance(payload, dict) else {}
        candidate = {key: str(value) for key, value in candidate.items()}
        violations = {key: _issues(text, allowed, citation_ids) for key, text in candidate.items()}
        violations = {key: items for key, items in violations.items() if items}
        if not violations:
            narrative = candidate
            break
        summary = "；".join(f"{key}: {', '.join(items[:3])}"
                            for key, items in list(violations.items())[:3])
        retry_hint = (f"上次输出未通过白名单校验：{summary}。"
                      "请把数字改为 {{参数id}} 占位符，并且只使用引用清单中的编号。")

    if narrative is None:
        narrative, dropped = _sanitize(candidate, allowed, citation_ids)
        source = "sanitized"
    else:
        dropped = 0
        source = "llm"

    ctx["narrative"] = narrative
    return {"type": "llm", "output_ref": "narrative", "whitelist": source,
            "attempts": attempts, "sentences_dropped": dropped}
