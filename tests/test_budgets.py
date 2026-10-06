"""C1~C6 计算工具单元测试（期望值独立手算，docs/11 §1 L1）。"""
import pytest

from app.tools.calc.budgets import (
    DataInput,
    MassInput,
    PowerInput,
    data_budget,
    mass_budget,
    power_budget,
)
from app.tools.calc.eps import EpsInput, eps_sizing
from app.tools.calc.link import LinkInput, link_budget
from app.tools.calc.orbit import OrbitInput, orbit_coverage


def test_mass_budget():
    result = mass_budget(MassInput(
        items=[
            {"name": "载荷", "mass_kg": 18.0, "source_ref": "x"},
            {"name": "电源", "mass_kg": 12.0, "source_ref": "x"},
            {"name": "结构", "mass_kg": 14.0, "source_ref": "x"},
        ],
        propellant_kg=3.0,
        margin_policy={"phase": "方案", "pct": 0.2},
    ))
    assert result.dry_mass_kg == pytest.approx(44.0)
    assert result.total_kg == pytest.approx(47.0)
    assert result.margin_mass_kg == pytest.approx(9.4)
    assert result.total_with_margin_kg == pytest.approx(56.4)


def test_power_budget():
    result = power_budget(PowerInput(
        loads=[
            {"name": "通信", "phase": "both", "power_w": 30.0, "duty_pct": 100},
            {"name": "载荷", "phase": "sun", "power_w": 45.0, "duty_pct": 50},
            {"name": "加热", "phase": "ecl", "power_w": 10.0, "duty_pct": 100},
        ],
        t_orbit_min=94.6,
        t_ecl_min=35.6,
        dod=0.3,
        eta_out=0.9,
    ))
    assert result.p_sun_w == pytest.approx(52.5)
    assert result.p_ecl_w == pytest.approx(40.0)
    assert result.p_avg_w == pytest.approx((52.5 * 59.0 + 40.0 * 35.6) / 94.6)
    assert result.e_ecl_wh == pytest.approx(40.0 * 35.6 / 60.0)
    assert result.battery_capacity_wh == pytest.approx((40.0 * 35.6 / 60.0) / (0.3 * 0.9))


def test_data_budget():
    result = data_budget(DataInput(
        rate_mbps=120.0,
        imaging_min_per_orbit=6.0,
        compression_ratio=3.0,
        downlink_rate_mbps=100.0,
        downlink_window_min_per_day=40.0,
        orbits_per_day=15.2,
        storage_cycles=2,
    ))
    assert result.per_orbit_gb == pytest.approx(1.8)
    assert result.per_day_gb == pytest.approx(1.8 * 15.2)
    assert result.downlink_capacity_gb == pytest.approx(30.0)
    assert result.storage_required_gb == pytest.approx(3.6)  # max(2×1.8, 27.36−30 → 0)


def test_power_budget_rejects_invalid_eclipse():
    with pytest.raises(Exception):
        PowerInput(
            loads=[{"name": "x", "phase": "sun", "power_w": 1.0, "duty_pct": 100}],
            t_orbit_min=90.0,
            t_ecl_min=90.0,
            dod=0.3,
            eta_out=0.9,
        )


def test_orbit_coverage_sso_500km():
    """500km SSO（i=97.4°）：周期 ≈94.6 min，交点退行 ≈0.9856°/day，每日≈15.2 圈。"""
    result = orbit_coverage(OrbitInput(alt_km=500, inc_deg=97.4,
                                       station_lat=40.0, station_lon=116.0))
    assert result.period_min == pytest.approx(94.6, abs=1.0)
    assert result.sso_ok is True
    assert abs(result.nodal_precession_deg_day - 0.9856) < 0.05
    assert result.orbits_per_day == pytest.approx(15.2, abs=0.3)
    assert result.windows_per_day >= 2
    assert result.revisit_avg_h is not None
    assert result.max_gap_h is not None


def test_link_budget_hand_calc():
    """手算：10 GHz / 1000 km / EIRP 40 / G-T 5 / 10 Mbps → Lfs≈172.45, Eb/N0≈31.15。"""
    result = link_budget(LinkInput(
        freq_ghz=10.0, slant_km=1000.0, eirp_dbw=40.0, gt_db_per_k=5.0,
        data_rate_kbps=10000.0, required_ebn0_db=10.0,
    ))
    assert result.fs_loss_db == pytest.approx(172.45, abs=0.1)
    assert result.ebn0_db == pytest.approx(31.15, abs=0.15)
    assert result.margin_db == pytest.approx(21.15, abs=0.15)


def test_eps_sizing_hand_calc():
    """手算：EOL 200W、3 年、年衰减 2% → BOL≈212.5W；效率链后面积≈0.748 m²。"""
    result = eps_sizing(EpsInput(
        p_eol_w=200.0, life_years=3.0, degradation_per_year=0.02,
        cell_efficiency=0.30, packing_factor=0.85,
    ))
    assert result.p_bol_w == pytest.approx(212.5, abs=0.5)
    assert result.sa_area_m2 == pytest.approx(0.748, abs=0.01)
