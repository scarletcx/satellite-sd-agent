"""V1~V4 校验规则测试（docs/11 §1 L1）。"""
from app.tools.calc.budgets import MassInput, mass_budget
from app.tools.calc.link import LinkInput, link_budget
from app.validation.history import v5_history
from app.validation.recompute import v2_recompute
from app.validation.rules import (
    v1_checks,
    v3_data_closure,
    v3_link_margin,
    v3_power_closure,
    v4_power_limit,
)
from app.validation.sensitivity import v6_sensitivity

_POWER_INPUTS = {"power": {"t_orbit_min": 94.6, "t_ecl_min": 35.6,
                           "dod": 0.30, "eta_out": 0.90}}


def _power_params() -> dict:
    """与 _POWER_INPUTS 自洽的一组合法功耗参数（p_sun 52.5 / p_ecl 40 W）。"""
    t_sun, t_ecl, orbit = 94.6 - 35.6, 35.6, 94.6
    p_sun, p_ecl = 52.5, 40.0
    energy = p_ecl * t_ecl / 60.0
    return {
        "power.p_sun_w": p_sun,
        "power.p_ecl_w": p_ecl,
        "power.p_avg_w": (p_sun * t_sun + p_ecl * t_ecl) / orbit,
        "power.e_ecl_wh": energy,
        "power.battery_capacity_wh": energy / (0.30 * 0.90),
    }


def test_v3_power_closure_passes_for_consistent_params():
    findings = v3_power_closure(_power_params(), _POWER_INPUTS)
    assert findings and all(item["status"] == "pass" for item in findings)


def test_v3_power_closure_blocks_tampered_average():
    params = _power_params()
    params["power.p_avg_w"] += 5.0  # 篡改平均功耗
    findings = v3_power_closure(params, _POWER_INPUTS)
    assert any(item["status"] == "block" and item["param_id"] == "power.p_avg_w"
               for item in findings)


def test_v3_power_closure_blocks_battery_mismatch():
    params = _power_params()
    params["power.battery_capacity_wh"] *= 1.2  # 电池容量虚高
    findings = v3_power_closure(params, _POWER_INPUTS)
    assert any(item["status"] == "block" and item["param_id"] == "power.battery_capacity_wh"
               for item in findings)


def test_v3_data_closure_and_storage_floor():
    params = {
        "data.per_orbit_gb": 1.8,
        "data.per_day_gb": 1.8 * 15.2846,
        "data.downlink_capacity_gb": 30.0,
        "data.storage_required_gb": 3.6,
        "orbit.orbits_per_day": 15.2846,
    }
    inputs = {"data": {"downlink_rate_mbps": 100.0, "downlink_window_min_per_day": 40.0}}
    findings = v3_data_closure(params, inputs)
    assert findings and all(item["status"] == "pass" for item in findings)

    params["data.storage_required_gb"] = 0.5  # 小于单圈数据量
    findings = v3_data_closure(params, inputs)
    assert any(item["status"] == "block" and "存储需求" in item["message"] for item in findings)


def test_v3_link_margin_threshold():
    assert v3_link_margin({"link.margin_db": 6.0}, {"link": {"min_margin_db": 3.0}})[0]["status"] == "pass"
    assert v3_link_margin({"link.margin_db": 1.2}, {"link": {"min_margin_db": 3.0}})[0]["status"] == "block"


def test_v4_power_limit_block():
    findings = v4_power_limit({"power.p_avg_w": 90.0}, {"power_limit_w": 60.0})
    assert findings[0]["status"] == "block"
    findings = v4_power_limit({"power.p_avg_w": 40.0}, {"power_limit_w": 60.0})
    assert findings[0]["status"] == "pass"


def test_v4_limit_waived_by_human_review():
    """人工放行（status=verified）后：超限降级为 warn 并标记豁免。"""
    findings = v4_power_limit({"power.p_avg_w": 90.0}, {"power_limit_w": 60.0},
                              {"power.p_avg_w": "verified"})
    assert findings[0]["status"] == "warn"
    assert findings[0]["evidence"]["waived"] is True

    from app.validation.rules import v4_mass_limit

    findings = v4_mass_limit({"mass.total_with_margin": 79.2}, {"mass_limit_kg": 70.0},
                             {"mass.total_with_margin": "verified"})
    assert findings[0]["status"] == "warn" and "豁免" in findings[0]["message"]


def test_v1_blocks_unconfirmed_inputs():
    params = [
        {"id": "input.mass", "value": 0.0, "unit": "1", "source_type": "model",
         "source_ref": "S4", "status": "draft"},
    ]
    findings = v1_checks(params, refs={"calc": set(), "assumption": set()})
    assert any(item["status"] == "block" and "未完成人工确认" in item["message"]
               for item in findings)


def test_v1_blocks_missing_calc_reference():
    params = [
        {"id": "mass.total", "value": 66.0, "unit": "kg", "source_type": "calc",
         "source_ref": "calc-不存在", "status": "proposed"},
    ]
    findings = v1_checks(params, refs={"calc": {"calc-20261006-0001"}, "assumption": set()})
    assert any(item["status"] == "block" and "计算记录不存在" in item["message"]
               for item in findings)


def _mass_record():
    inputs = {
        "items": [
            {"name": "载荷", "mass_kg": 20.0, "source_ref": "x"},
            {"name": "平台", "mass_kg": 30.0, "source_ref": "x"},
        ],
        "propellant_kg": 2.0,
        "margin_policy": {"phase": "方案", "pct": 0.2},
    }
    outputs = mass_budget(MassInput(**inputs)).model_dump()
    return {"id": "calc-test-0001", "tool": "calc.mass_budget", "inputs": inputs, "outputs": outputs}


def _link_record(required_ebn0_db: float = 27.0):
    inputs = {
        "freq_ghz": 10.0, "slant_km": 1000.0, "eirp_dbw": 40.0, "gt_db_per_k": 5.0,
        "data_rate_kbps": 10000.0, "required_ebn0_db": required_ebn0_db, "min_margin_db": 3.0,
    }
    outputs = link_budget(LinkInput(**inputs)).model_dump()
    return {"id": "calc-test-0002", "tool": "calc.link_budget", "inputs": inputs, "outputs": outputs}


def test_v2_passes_for_consistent_records():
    findings = v2_recompute([_mass_record(), _link_record()])
    assert findings and all(item["rule_id"] == "V2" for item in findings)
    assert findings[0]["status"] == "pass"


def test_v2_blocks_tampered_output():
    record = _mass_record()
    record["outputs"]["total_with_margin_kg"] = 44.0  # 篡改汇总值
    findings = v2_recompute([record])
    assert any(item["status"] == "block" and "独立重算不一致" in item["message"]
               for item in findings)


def test_v6_warns_when_mass_growth_breaks_limit():
    findings = v6_sensitivity([_mass_record()], {"mass_limit_kg": 62.5})
    assert any(item["rule_id"] == "V6" and item["status"] == "warn" for item in findings)


def test_v6_passes_when_robust():
    findings = v6_sensitivity([_mass_record()], {"mass_limit_kg": 80.0})
    assert any(item["rule_id"] == "V6" and item["status"] == "pass" for item in findings)


def test_v6_warns_when_extra_loss_breaks_link_margin():
    findings = v6_sensitivity([_link_record()], {})
    assert any(item["rule_id"] == "V6" and item["status"] == "warn"
               and item["param_id"] == "link.margin_db" for item in findings)


def _reference() -> dict:
    return {
        "source": "test",
        "sample_n": {"mass": 1, "power": 1},
        "ranges": {"mass_kg": {"p10": 10, "p90": 100},
                   "power_w": {"p10": 20, "p90": 200}},
    }


def test_v5_out_of_range_warns():
    findings = v5_history({"mass.total_with_margin": 500.0, "power.p_avg_w": 50.0},
                          reference=_reference())
    assert any(item["status"] == "warn" and "P90" in item["message"] for item in findings)


def test_v5_in_range_passes():
    findings = v5_history({"mass.total_with_margin": 60.0, "power.p_avg_w": 50.0},
                          reference=_reference())
    assert findings[0]["status"] == "pass"
