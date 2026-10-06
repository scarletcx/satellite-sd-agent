"""docx 渲染（docxtpl，ADR-0005）：IR + 叙述 → Word。

约定：数字只来自 IR；模板占位符与数据源映射见 docs/10 §2。
"""
from __future__ import annotations

from pathlib import Path

from docxtpl import DocxTemplate

from app.config import BASE_DIR

TEMPLATE_DIR = BASE_DIR / "templates"

# 各类参数展示小数位
_DECIMALS = {"mass": 1, "power": 1, "data": 2}


def format_value(param_id: str, value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:.0f}"
    decimals = _DECIMALS.get(param_id.split(".", 1)[0], 2)
    return f"{value:.{decimals}f}"


def build_context(
    mission: dict,
    params: list[dict],
    system_design: dict,
    assumptions: list[dict],
    narrative: dict,
    citations: list[dict] | None = None,
) -> dict:
    constraints = mission.get("constraints", {}) or {}
    context: dict = {
        "mission": {
            "goal": mission.get("goal", ""),
            "orbit_type": constraints.get("orbit_type", ""),
            "altitude_km": constraints.get("altitude_km", ""),
            "lifetime_years": constraints.get("lifetime_years", ""),
        },
        "narrative": narrative,
        "citations": citations or [],
        "assumptions": assumptions,
        "candidates": [],
    }

    # 参数按 id 路径嵌套：power.sa.area → context["power"]["sa"]["area"]["value"]
    for param in params:
        node = context
        parts = param["id"].split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = {
            "value": format_value(param["id"], param["value"], param["unit"]),
            "unit": param["unit"],
            "name": param["name"],
            "source_ref": param["source_ref"],
        }

    # 预算行（按前缀分组，来源保留计算记录 id）
    for prefix, key in (("mass", "mass_items"), ("power", "power_items"), ("data", "data_items"),
                        ("orbit", "orbit_items"), ("link", "link_items")):
        context[key] = [
            {
                "name": param["name"],
                "value": format_value(param["id"], param["value"], param["unit"]),
                "unit": param["unit"],
                "source_ref": param["source_ref"],
            }
            for param in params if param["id"].startswith(prefix + ".")
        ]

    configuration = (system_design or {}).get("configuration", {})
    envelope = configuration.get("envelope_mm", {})
    context["config"] = {"type": configuration.get("type", ""), "notes": configuration.get("notes", "")}
    context["envelope"] = {axis: envelope.get(axis, "") for axis in ("x", "y", "z")}
    context["subsystems"] = (system_design or {}).get("subsystems", [])
    return context


def render_document(template_version: str, context: dict, out_path: Path) -> Path:
    template_path = TEMPLATE_DIR / f"{template_version}.docx"
    if not template_path.exists():
        raise FileNotFoundError(f"模板不存在：{template_path}（先执行 make template）")
    doc = DocxTemplate(str(template_path))
    doc.render(context)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
