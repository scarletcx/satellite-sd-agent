"""C5 轨道交叉验证测试（第三方库复算，docs/06 §3）。"""
import pytest

from app.tools.calc.orbit import OrbitInput, orbit_coverage
from app.validation.orbit_crosscheck import (
    crosscheck_orbit,
    skyfield_available,
    v2_orbit_crosscheck,
)

pytestmark = pytest.mark.skipif(not skyfield_available(),
                                reason="skyfield 未安装（可选依赖）")


def test_crosscheck_agrees_with_analytic_model():
    """解析模型 vs SGP4：周期 ≤0.5%、交点退行 ≤2%（实测 ≈0.06% / ≈0.2%）。"""
    for alt, inc in ((500.0, 97.4), (800.0, 98.6)):
        analytic = orbit_coverage(OrbitInput(alt_km=alt, inc_deg=inc,
                                             station_lat=40.0, station_lon=116.0))
        reference = crosscheck_orbit(alt, inc)
        period_diff = abs(analytic.period_min - reference["period_min"]) / reference["period_min"] * 100
        drift_diff = (abs(analytic.nodal_precession_deg_day
                          - reference["nodal_precession_deg_day"])
                      / abs(reference["nodal_precession_deg_day"]) * 100)
        assert period_diff <= 0.5, (alt, inc, period_diff)
        assert drift_diff <= 2.0, (alt, inc, drift_diff)
        assert reference["crossings"] >= 10


def _orbit_record():
    analytic = orbit_coverage(OrbitInput(alt_km=500.0, inc_deg=97.4,
                                         station_lat=40.0, station_lon=116.0))
    return {
        "id": "calc-test-orbit",
        "tool": "calc.orbit",
        "inputs": {"alt_km": 500.0, "inc_deg": 97.4},
        "outputs": analytic.model_dump(),
    }


def test_v2_crosscheck_passes_for_consistent_record():
    findings = v2_orbit_crosscheck([_orbit_record()])
    assert findings and findings[0]["status"] == "pass"
    assert findings[0]["evidence"]["rule"] == "C5-crosscheck"


def test_v2_crosscheck_blocks_tampered_precession():
    record = _orbit_record()
    record["outputs"]["nodal_precession_deg_day"] *= 1.4  # 篡改退行率
    findings = v2_orbit_crosscheck([record])
    assert findings[0]["status"] == "block"
    assert findings[0]["evidence"]["drift_diff_pct"] > 2.0
