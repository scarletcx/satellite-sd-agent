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
from app.validation.orbit_crosscheck import v2_orbit_crosscheck
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
        if p.get("status") in ("draft", "rejected"):
            findings.append(_finding("V1", "block", p.get("id"),
                                     f"参数状态为 {p['status']}，未完成人工确认",
                                     field="status", got=p.get("status")))
            continue
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


def v4_mass_limit(params: dict[str, float], constraints: dict,
                  statuses: dict[str, str] | None = None) -> list[dict]:
    """V4：整星质量上限约束。人工已放行（status=verified）的超限降级为 warn（豁免留痕）。"""
    limit = (constraints or {}).get("mass_limit_kg")
    if not limit or "mass.total_with_margin" not in params:
        return []
    actual = params["mass.total_with_margin"]
    waived = (statuses or {}).get("mass.total_with_margin") == "verified"
    if actual <= limit:
        status, message = "pass", f"整星质量（含余量）{actual:.2f} kg ≤ 上限 {limit} kg"
    elif waived:
        status, message = ("warn",
                           f"整星质量（含余量）{actual:.2f} kg 超出上限 {limit} kg，"
                           "已由人工评审放行（豁免记录见审计日志）")
    else:
        status, message = ("block",
                           f"整星质量（含余量）{actual:.2f} kg 超出上限 {limit} kg")
    return [_finding("V4", status, "mass.total_with_margin", message,
                     expected=limit, actual=actual, tolerance_pct=0.0, waived=waived)]


def v4_power_limit(params: dict[str, float], constraints: dict,
                   statuses: dict[str, str] | None = None) -> list[dict]:
    """V4：轨道平均功耗上限约束。人工已放行的超限降级为 warn（豁免留痕）。"""
    limit = (constraints or {}).get("power_limit_w")
    if not limit or "power.p_avg_w" not in params:
        return []
    actual = params["power.p_avg_w"]
    waived = (statuses or {}).get("power.p_avg_w") == "verified"
    if actual <= limit:
        status, message = "pass", f"轨道平均功耗 {actual:.2f} W ≤ 上限 {limit} W"
    elif waived:
        status, message = ("warn",
                           f"轨道平均功耗 {actual:.2f} W 超出上限 {limit} W，"
                           "已由人工评审放行（豁免记录见审计日志）")
    else:
        status, message = ("block",
                           f"轨道平均功耗 {actual:.2f} W 超出上限 {limit} W")
    return [_finding("V4", status, "power.p_avg_w", message,
                     expected=limit, actual=actual, tolerance_pct=0.0, waived=waived)]


def _close(recorded: float, expected: float) -> float:
    return abs(recorded - expected) / max(abs(expected), 1e-9)


def v3_power_closure(params: dict[str, float], inputs: dict | None) -> list[dict]:
    """V3：功耗链路闭合（阴影期能量 → 电池容量 → 轨道平均功耗）。"""
    required = {"power.p_sun_w", "power.p_ecl_w", "power.p_avg_w",
                "power.e_ecl_wh", "power.battery_capacity_wh"}
    if not required <= params.keys():
        return [_finding("V3", "block", "power.p_avg_w", "功耗预算缺少必要参数，无法执行闭合校验")]
    power_input = ((inputs or {}).get("power") or {})
    t_orbit = float(power_input.get("t_orbit_min") or 0)
    t_ecl = float(power_input.get("t_ecl_min") or 0)
    dod = float(power_input.get("dod") or 0)
    eta = float(power_input.get("eta_out") or 0)

    findings: list[dict] = []
    if t_orbit > 0 and t_ecl > 0:
        expected_avg = (params["power.p_sun_w"] * (t_orbit - t_ecl)
                        + params["power.p_ecl_w"] * t_ecl) / t_orbit
        diff = _close(params["power.p_avg_w"], expected_avg)
        findings.append(_finding(
            "V3", "pass" if diff <= TOLERANCE_PCT else "block", "power.p_avg_w",
            f"轨道平均功耗闭合（记录 {params['power.p_avg_w']:.2f} W vs 加权 {expected_avg:.2f} W）",
            expected=expected_avg, actual=params["power.p_avg_w"], diff_pct=diff * 100))

        expected_energy = params["power.p_ecl_w"] * t_ecl / 60.0
        diff = _close(params["power.e_ecl_wh"], expected_energy)
        findings.append(_finding(
            "V3", "pass" if diff <= TOLERANCE_PCT else "block", "power.e_ecl_wh",
            f"阴影期能耗闭合（记录 {params['power.e_ecl_wh']:.3f} Wh vs 功率×时长 {expected_energy:.3f} Wh）",
            expected=expected_energy, actual=params["power.e_ecl_wh"], diff_pct=diff * 100))

        if dod > 0 and eta > 0:
            expected_battery = params["power.e_ecl_wh"] / (dod * eta)
            diff = _close(params["power.battery_capacity_wh"], expected_battery)
            findings.append(_finding(
                "V3", "pass" if diff <= TOLERANCE_PCT else "block", "power.battery_capacity_wh",
                (f"电池容量闭合（记录 {params['power.battery_capacity_wh']:.2f} Wh vs "
                 f"能耗/(DOD×效率) {expected_battery:.2f} Wh）"),
                expected=expected_battery, actual=params["power.battery_capacity_wh"],
                diff_pct=diff * 100))
    return findings


def v3_data_closure(params: dict[str, float], inputs: dict | None) -> list[dict]:
    """V3：数据量链路闭合（单圈×每日圈次 = 每日；下行能力按速率×窗口；存储 ≥ 单圈）。"""
    required = {"data.per_orbit_gb", "data.per_day_gb",
                "data.downlink_capacity_gb", "data.storage_required_gb"}
    if not required <= params.keys():
        return [_finding("V3", "block", "data.per_day_gb", "数据量预算缺少必要参数，无法执行闭合校验")]
    data_input = ((inputs or {}).get("data") or {})
    findings: list[dict] = []

    orbits = params.get("orbit.orbits_per_day") or float(data_input.get("orbits_per_day") or 0)
    if orbits > 0:
        expected_day = params["data.per_orbit_gb"] * orbits
        diff = _close(params["data.per_day_gb"], expected_day)
        findings.append(_finding(
            "V3", "pass" if diff <= TOLERANCE_PCT else "block", "data.per_day_gb",
            f"每日数据量闭合（记录 {params['data.per_day_gb']:.3f} Gb vs 单圈×圈次 {expected_day:.3f} Gb）",
            expected=expected_day, actual=params["data.per_day_gb"], diff_pct=diff * 100))

    rate = float(data_input.get("downlink_rate_mbps") or 0)
    window = float(data_input.get("downlink_window_min_per_day") or 0)
    if rate > 0 and window > 0:
        expected_downlink = rate * window * 60.0 / 8000.0
        diff = _close(params["data.downlink_capacity_gb"], expected_downlink)
        findings.append(_finding(
            "V3", "pass" if diff <= TOLERANCE_PCT else "block", "data.downlink_capacity_gb",
            (f"下行能力闭合（记录 {params['data.downlink_capacity_gb']:.3f} Gb vs "
             f"速率×窗口 {expected_downlink:.3f} Gb）"),
            expected=expected_downlink, actual=params["data.downlink_capacity_gb"],
            diff_pct=diff * 100))

    if params["data.storage_required_gb"] < params["data.per_orbit_gb"]:
        findings.append(_finding(
            "V3", "block", "data.storage_required_gb",
            (f"存储需求 {params['data.storage_required_gb']:.3f} Gb 小于单圈数据量 "
             f"{params['data.per_orbit_gb']:.3f} Gb，无法保障过境间数据保持")))
    return findings


def v3_link_margin(params: dict[str, float], inputs: dict | None) -> list[dict]:
    """V3：链路余量阈值检查（默认 ≥3 dB，可由输入覆盖）。"""
    if "link.margin_db" not in params:
        return []
    threshold = float(((inputs or {}).get("link") or {}).get("min_margin_db") or 3.0)
    margin = params["link.margin_db"]
    status = "pass" if margin >= threshold else "block"
    message = (f"链路余量 {margin:.2f} dB ≥ 阈值 {threshold:.1f} dB" if status == "pass"
               else f"链路余量 {margin:.2f} dB 低于阈值 {threshold:.1f} dB")
    return [_finding("V3", status, "link.margin_db", message,
                     expected=threshold, actual=margin, tolerance_pct=0.0)]


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
                   records: list[dict] | None = None, inputs: dict | None = None) -> list[dict]:
    """执行全部已实现规则（按 V1→V7 顺序）；params 为参数 dict 列表（含 id/value/unit/source_*）。

    records = CalculationRecord 摘要（V2 独立重算 / V6 敏感性使用）。
    inputs  = S4 落库的分组设计输入（V3 功耗/数据量闭合与链路阈值使用）。
    """
    values = {p["id"]: p["value"] for p in params}
    statuses = {p["id"]: p.get("status") for p in params}
    findings: list[dict] = []
    findings += v1_checks(params, refs)
    if records is not None:
        findings += v2_recompute(records)
        findings += v2_orbit_crosscheck(records)
    findings += v3_mass_closure(values)
    findings += v3_mass_margin(values)
    findings += v3_power_closure(values, inputs)
    findings += v3_data_closure(values, inputs)
    findings += v3_link_margin(values, inputs)
    findings += v4_mass_limit(values, constraints, statuses)
    findings += v4_power_limit(values, constraints, statuses)
    findings += v5_history(values)
    findings += v6_sensitivity(records or [], constraints)
    findings += v7_assumptions(assumptions or [])

    # 人工豁免：已由工程师接受过的参数，重跑校验时命中阻断 → 降级为 warn（保留证据）
    waived = {p["id"] for p in params if p.get("waived")}
    if waived:
        for finding in findings:
            if finding["status"] == "block" and finding.get("param_id") in waived:
                finding["status"] = "warn"
                finding["message"] = finding["message"] + "（已由人工评审豁免）"
                finding["evidence"] = {**finding.get("evidence", {}), "waived": True}
    return findings


def summarize(findings: list[dict]) -> dict:
    summary = {"pass": 0, "warn": 0, "block": 0}
    for f in findings:
        summary[f["status"]] = summary.get(f["status"], 0) + 1
    return summary
