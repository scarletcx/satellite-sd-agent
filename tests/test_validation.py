"""V2 / V5 / V6 校验规则测试（docs/11 §1 L1）。"""
from app.tools.calc.budgets import MassInput, mass_budget
from app.tools.calc.link import LinkInput, link_budget
from app.validation.history import v5_history
from app.validation.recompute import v2_recompute
from app.validation.sensitivity import v6_sensitivity


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
