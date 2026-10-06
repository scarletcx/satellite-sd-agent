"""校验规则实现。

每个规则返回 finding：
    {"rule_id": "V3", "status": "pass|warn|block", "param_id": str|None,
     "message": str, "evidence": {...}}
阈值来源于 docs/06 §3，初值可标定。
"""
from __future__ import annotations

from typing import Any

from app.tools.calc.units import UNIT_ENUM
from app.validation.history import v5_history
from app.validation.recompute import v2_recompute
from app.validation.sensitivity import v6_sensitivity

TOLERANCE_PCT = 0.005      # 汇总 = 分项和 的容差
MASS_MARGIN_MIN = 20.0     # 方案期质量余量阈值（百分数）
MASS_MARGIN_WARN = 10.0


def _finding(rule_id: str, status: str, param_id: str | None, message: str, **evidence: Any) -> dict:
    return {"rule_id": rule_id, "status": status, "param_id": param_id, "message": message, "evidence": evidence}


def v1_checks(params: list[dict], refs: dict | None = None) -> list[dict]:
    """V1：单位枚举 / 溯源字段完整性 / 引用完整性（入库前强制）。

    refs = {"calc": set(计算记录 id), "assumption": set(假设 id)}；
    引用不存在的记录 → block（对应 ADV-01「数字没有有效计算过程」）。
    """
    findings: list[dict] = []
    refs = refs or {}
    for p in params:
        if p.get("unit") not in UNIT_ENUM:
            findings.append(_finding("V1", "block", p.get("id"), f"单位不在枚举内：{p.get('unit')!r}",
                                     field="unit", got=p.get("unit")))
        if not p.get("source_type") or not p.get("source_ref"):
            findings.append(_finding("V1", "block", p.get("id"), "缺少 source_type / source_ref",
                                     field="source", got=None))
            continue
        source_type, source_ref = p["source_type"], p["source_ref"]
        if source_type == "calc" and refs.get("calc") is not None and source_ref not in refs["calc"]:
            findings.append(_finding("V1", "block", p.get("id"),
                                     f"source_ref 指向的计算记录不存在：{source_ref}（数字缺少可复算依据）",
                                     field="source_ref", got=source_ref))
        if (source_type == "assumption" and refs.get("assumption") is not None
                and source_ref not in refs["assumption"]):
            findings.append(_finding("V1", "block", p.get("id"),
                                     f"source_ref 指向的假设不存在：{source_ref}",
                                     field="source_ref", got=source_ref))
    if not findings:
        findings.append(_finding("V1", "pass", None, f"{len(params)} 个参数的单位、溯源与引用完整性通过"))
    return findings


def v3_mass_closure(params: dict[str, float]) -> list[dict]:
    """V3：质量预算闭合（干重 + 推进剂 = 总重，±0.5%）。"""
    if not {"mass.dry", "mass.propellant", "mass.total"} <= params.keys():
        return [_finding("V3", "block", "mass.total", "质量预算缺少必要参数，无法执行闭合校验")]
    expected = params["mass.dry"] + params["mass.propellant"]
    actual = params["mass.total"]
    diff_pct = abs(expected - actual) / max(abs(actual), 1e-9)
    status = "pass" if diff_pct <= TOLERANCE_PCT else "block"
    return [_finding("V3", status, "mass.total",
                     f"质量预算闭合校验（分项和 {expected:.2f} kg vs 汇总 {actual:.2f} kg）",
                     expected=expected, actual=actual, tolerance_pct=TOLERANCE_PCT * 100)]


def v3_mass_margin(params: dict[str, float]) -> list[dict]:
    """V3：质量余量阈值（方案期 ≥20%）。"""
    if "mass.margin_pct" not in params:
        return []
    margin = params["mass.margin_pct"]
    if margin >= MASS_MARGIN_MIN:
        status, message = "pass", f"质量余量 {margin:.0f}% 满足方案期要求（≥{MASS_MARGIN_MIN:.0f}%）"
    elif margin >= MASS_MARGIN_WARN:
        status, message = "warn", f"质量余量 {margin:.0f}% 低于方案期要求（≥{MASS_MARGIN_MIN:.0f}%）"
    else:
        status, message = "block", f"质量余量 {margin:.0f}% 严重不足（<{MASS_MARGIN_WARN:.0f}%）"
    return [_finding("V3", status, "mass.margin_pct", message, margin=margin, threshold=MASS_MARGIN_MIN)]


def v4_mass_limit(params: dict[str, float], constraints: dict) -> list[dict]:
    """V4（lite）：整星质量上限约束。"""
    limit = (constraints or {}).get("mass_limit_kg")
    if not limit or "mass.total_with_margin" not in params:
        return []
    actual = params["mass.total_with_margin"]
    status = "pass" if actual <= limit else "block"
    message = (f"整星质量（含余量）{actual:.2f} kg ≤ 上限 {limit} kg" if status == "pass"
               else f"整星质量（含余量）{actual:.2f} kg 超出上限 {limit} kg")
    return [_finding("V4", status, "mass.total_with_margin", message,
                     expected=limit, actual=actual, tolerance_pct=0.0)]


def v7_assumptions(assumptions: list[dict]) -> list[dict]:
    """V7：假设台账核对。未确认假设 → warn（入稿前需人工确认；确认门禁流程为后续项）。"""
    if not assumptions:
        return []
    open_items = [a for a in assumptions if a.get("status") == "open"]
    if not open_items:
        return [_finding("V7", "pass", None, f"{len(assumptions)} 条假设均已确认")]
    names = "；".join(f"{a.get('id')}: {a.get('content', '')[:24]}" for a in open_items[:3])
    return [_finding("V7", "warn", None,
                     f"{len(open_items)} 条假设未确认（入稿前需人工确认）：{names}",
                     open_assumptions=[a.get("id") for a in open_items])]


def run_validation(params: list[dict], constraints: dict,
                   refs: dict | None = None, assumptions: list[dict] | None = None,
                   records: list[dict] | None = None) -> list[dict]:
    """执行全部已实现规则（按 V1→V7 顺序）；params 为参数 dict 列表（含 id/value/unit/source_*）。

    records = CalculationRecord 摘要（V2 独立重算 / V6 敏感性使用）。
    """
    values = {p["id"]: p["value"] for p in params}
    findings: list[dict] = []
    findings += v1_checks(params, refs)
    if records is not None:
        findings += v2_recompute(records)
    findings += v3_mass_closure(values)
    findings += v3_mass_margin(values)
    findings += v4_mass_limit(values, constraints)
    findings += v5_history(values)
    findings += v6_sensitivity(records or [], constraints)
    findings += v7_assumptions(assumptions or [])
    return findings


def summarize(findings: list[dict]) -> dict:
    summary = {"pass": 0, "warn": 0, "block": 0}
    for f in findings:
        summary[f["status"]] = summary.get(f["status"], 0) + 1
    return summary
