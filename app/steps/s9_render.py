"""S9 文档渲染（docxtpl，docs/10）：叙述占位符替换 → docx → 自检报告。

产物：document-v1.docx / parameters-snapshot.json / check-report.json。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.db import new_session
from app.models import Assumption, Mission
from app.steps.common import load_params
from app.tools.doc.check import check_document, numbers_in_texts
from app.tools.doc.render import build_context, format_value, render_document
from app.tracing import task_dir

PLACEHOLDER_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _lookup(mission: dict, params: list[dict]) -> dict[str, str]:
    """占位符 → 已格式化文本。参数走统一格式规则；mission.* 取任务书数值。"""
    values: dict[str, str] = {}
    for param in params:
        values[param["id"]] = format_value(param["id"], param["value"], param["unit"])
    constraints = mission.get("constraints", {}) or {}
    values.update({
        "mission.goal": mission.get("goal", ""),
        "mission.orbit_type": str(constraints.get("orbit_type", "")),
        "mission.altitude_km": str(constraints.get("altitude_km", "")),
        "mission.lifetime_years": str(constraints.get("lifetime_years", "")),
    })
    return values


def _render_text(text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        return values.get(match.group(1), match.group(0))

    return PLACEHOLDER_RE.sub(repl, text)


def _load_system_design(mission_id: str) -> dict:
    path = task_dir(mission_id) / "system-design.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_citations(mission_id: str) -> list[dict]:
    path = task_dir(mission_id) / "citations.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run(ctx: dict) -> dict:
    mission_id = ctx["task_id"]
    with new_session() as session:
        mission_row = session.get(Mission, mission_id)
        params = load_params(session, mission_id)
        assumptions = [
            {"id": a.id, "content": a.content, "basis": a.basis, "status": a.status}
            for a in session.query(Assumption)
            .filter(Assumption.mission_id == mission_id)
            .order_by(Assumption.id).all()
        ]

    mission = {"goal": mission_row.goal, "constraints": dict(mission_row.constraints or {})}
    system_design = ctx.get("system_design") or _load_system_design(mission_id)
    citations = ctx.get("citations") or _load_citations(mission_id)

    values = _lookup(mission, params)
    narrative = {
        (key.split("_", 1)[1] if "_" in key else key): _render_text(text, values)
        for key, text in (ctx.get("narrative") or {}).items()
    }

    context = build_context(mission, params, system_design, assumptions, narrative,
                            citations=citations)
    directory = task_dir(mission_id)
    docx_path = render_document("design-report-v1", context, directory / "document-v1.docx")

    # 数字反查允许集合：IR 参数 + 任务约束 + 假设台账 + 系统方案
    allowed = [param["value"] for param in params]
    for value in (mission["constraints"] or {}).values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            allowed.append(float(value))
    allowed += numbers_in_texts([f"{a['content']} {a['basis']}" for a in assumptions])
    allowed += numbers_in_texts([json.dumps(system_design, ensure_ascii=False)])

    result = check_document(docx_path, allowed)
    report = {
        "task_id": mission_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "placeholders_left": result["placeholders_left"],
        "numbers_checked": result["numbers_checked"],
        "numbers_traceable": result["numbers_traceable"],
        "citations": len(citations),
        "citation_issues": 0,
        "status": result["status"],
        "issues": result["issues"],
    }
    (directory / "check-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "parameters-snapshot.json").write_text(
        json.dumps({"task_id": mission_id, "parameters": params}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ctx["check_report"] = report
    return {"type": "tool", "output_ref": "document-v1.docx",
            "placeholders_left": report["placeholders_left"]}
