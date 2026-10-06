"""V2 独立重算（docs/06 §4 V2）：从 CalculationRecord 的原始输入重新推导输出。

第二实现刻意与 `app/tools/calc` 分开书写（不复用），用于发现
「计算记录被篡改 / 输出与输入不自洽」的问题；容差 0.5%。
"""
from __future__ import annotations

import math

from app.tools.calc.constants import C_M_S, E0_W_M2, K_DBW, MU_EARTH_KM3_S2, RE_KM

TOLERANCE_PCT = 0.5


def recompute(tool: str, inputs: dict) -> dict[str, float]:
    """独立推导（覆盖当前全部计算工具；未知工具返回空）。"""
    if tool == "calc.mass_budget":
        dry = 0.0
        for item in inputs["items"]:
            dry += float(item["mass_kg"])
        total = dry + float(inputs["propellant_kg"])
        margin = total * float(inputs["margin_policy"]["pct"])
        return {"dry_mass_kg": dry, "total_kg": total,
                "margin_mass_kg": margin, "total_with_margin_kg": total + margin}

    if tool == "calc.power_budget":
        p_sun = p_ecl = 0.0
        for load in inputs["loads"]:
            power = float(load["power_w"]) * float(load["duty_pct"]) / 100.0
            if load["phase"] in ("sun", "both"):
                p_sun += power
            if load["phase"] in ("ecl", "both"):
                p_ecl += power
        t_orbit = float(inputs["t_orbit_min"])
        t_ecl = float(inputs["t_ecl_min"])
        p_avg = (p_sun * (t_orbit - t_ecl) + p_ecl * t_ecl) / t_orbit
        e_ecl = p_ecl * t_ecl / 60.0
        battery = e_ecl / (float(inputs["dod"]) * float(inputs["eta_out"]))
        return {"p_sun_w": p_sun, "p_ecl_w": p_ecl, "p_avg_w": p_avg,
                "e_ecl_wh": e_ecl, "battery_capacity_wh": battery}

    if tool == "calc.data_budget":
        per_orbit = (float(inputs["rate_mbps"]) * float(inputs["imaging_min_per_orbit"]) * 60.0
                     / (8000.0 * float(inputs["compression_ratio"])))
        per_day = per_orbit * float(inputs["orbits_per_day"])
        downlink = (float(inputs["downlink_rate_mbps"])
                    * float(inputs["downlink_window_min_per_day"]) * 60.0 / 8000.0)
        storage = max(per_orbit * int(inputs.get("storage_cycles", 2)), max(0.0, per_day - downlink))
        return {"per_orbit_gb": per_orbit, "per_day_gb": per_day,
                "downlink_capacity_gb": downlink, "storage_required_gb": storage}

    if tool == "calc.eps":
        p_bol = (float(inputs["p_eol_w"])
                 / (1 - float(inputs["degradation_per_year"])) ** float(inputs["life_years"]))
        area = (p_bol / (E0_W_M2 * float(inputs["cell_efficiency"])
                         * float(inputs["packing_factor"])
                         * float(inputs.get("sun_angle_cos", 0.9)))
                * (1 + float(inputs.get("margin_pct", 0.1))))
        return {"p_bol_w": p_bol, "sa_area_m2": area}

    if tool == "calc.link_budget":
        wavelength = C_M_S / (float(inputs["freq_ghz"]) * 1e9)
        fs_loss = 20 * math.log10(4 * math.pi * float(inputs["slant_km"]) * 1000.0 / wavelength)
        ebn0 = (float(inputs["eirp_dbw"]) + float(inputs["gt_db_per_k"]) - fs_loss
                - float(inputs.get("rain_margin_db", 0.0))
                - float(inputs.get("other_losses_db", 0.0))
                - 10 * math.log10(float(inputs["data_rate_kbps"]) * 1000.0) - K_DBW)
        return {"fs_loss_db": fs_loss, "ebn0_db": ebn0,
                "margin_db": ebn0 - float(inputs["required_ebn0_db"])}

    if tool == "calc.orbit":
        semi_major = RE_KM + float(inputs["alt_km"])
        period_min = 2 * math.pi * math.sqrt(semi_major**3 / MU_EARTH_KM3_S2) / 60.0
        return {"period_min": period_min, "orbits_per_day": 86400.0 / (period_min * 60.0)}

    return {}


def v2_recompute(records: list[dict]) -> list[dict]:
    """records: [{id, tool, inputs, outputs}]；与记录值比对，不一致 → block。"""
    findings: list[dict] = []
    checked = 0
    for record in records:
        try:
            expected = recompute(record["tool"], record["inputs"] or {})
        except (KeyError, TypeError, ValueError) as exc:
            findings.append({
                "rule_id": "V2", "status": "block", "param_id": None,
                "message": f"独立重算失败（记录输入不完整）：{record['tool']} 缺少 {exc}",
                "evidence": {"record_id": record["id"], "error": str(exc)},
            })
            continue
        for key, value in expected.items():
            recorded = (record["outputs"] or {}).get(key)
            if recorded is None:
                continue
            checked += 1
            diff_pct = abs(float(recorded) - value) / max(abs(value), 1e-9) * 100
            if diff_pct > TOLERANCE_PCT:
                findings.append({
                    "rule_id": "V2", "status": "block", "param_id": None,
                    "message": (f"独立重算不一致：{record['tool']}.{key} 记录值 {float(recorded):.6g} "
                                f"vs 重算值 {value:.6g}（偏差 {diff_pct:.2f}%）"),
                    "evidence": {"record_id": record["id"], "key": key,
                                 "recorded": recorded, "recomputed": value, "diff_pct": diff_pct},
                })
    if not findings:
        findings.append({
            "rule_id": "V2", "status": "pass", "param_id": None,
            "message": f"{len(records)} 条计算记录独立重算一致（{checked} 项）",
            "evidence": {"records": len(records), "checked": checked},
        })
    return findings
