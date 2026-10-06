"""S5 预算与计算（确定性）：C5 轨道 → C1 质量 → C2 功耗 → C6 太阳翼 → C3 数据量 → C4 链路。

执行顺序按依赖驱动：C3 的 orbits_per_day 由 C5 输出覆盖（docs/06 §2 C3）。
每个数字都来自计算工具，并写入 CalculationRecord 与 DesignParameter（docs/05 §S5）。
"""
from __future__ import annotations

from app.db import new_session
from app.models import CalculationRecord, Mission
from app.orchestrator.ids import next_calc_ids
from app.steps.common import load_params, upsert_parameter
from app.tools.calc.budgets import (
    DataInput,
    MassInput,
    PowerInput,
    data_budget,
    mass_budget,
    power_budget,
)
from app.tools.calc.constants import FORMULA_VERSIONS
from app.tools.calc.eps import EpsInput, eps_sizing
from app.tools.calc.link import LinkInput, link_budget
from app.tools.calc.orbit import OrbitInput, orbit_coverage


def run(ctx: dict) -> dict:
    s4 = ctx["s4"]
    with new_session() as session:
        mission = session.get(Mission, ctx["task_id"])
        constraints = dict(mission.constraints or {})

    # ---- C5 轨道与覆盖 ----
    orbit_res = orbit_coverage(OrbitInput(**s4["orbit"]))
    # ---- C1 质量 ----
    mass_res = mass_budget(MassInput(**s4["mass"]))
    # ---- C2 功耗 ----
    power_res = power_budget(PowerInput(**s4["power"]))
    # ---- C4 链路 ----
    link_res = link_budget(LinkInput(**s4["link"]))
    # ---- C6 太阳翼（EOL 功率 = 轨道平均功耗 + 阴影期再充电功率）----
    life_years = float(constraints.get("lifetime_years") or 3)
    t_sun_h = max((s4["power"]["t_orbit_min"] - s4["power"]["t_ecl_min"]) / 60.0, 0.01)
    p_eol = power_res.p_avg_w + power_res.e_ecl_wh / t_sun_h
    eps_res = eps_sizing(EpsInput(p_eol_w=p_eol, life_years=life_years, **s4["eps"]))
    # ---- C3 数据量（orbits_per_day 采用 C5 结果）----
    data_input = dict(s4["data"])
    data_input["orbits_per_day"] = round(orbit_res.orbits_per_day, 4)
    data_res = data_budget(DataInput(**data_input))

    ctx["results"] = {
        "orbit": orbit_res.model_dump(),
        "mass": mass_res.model_dump(),
        "power": power_res.model_dump(),
        "eps": eps_res.model_dump(),
        "data": data_res.model_dump(),
        "link": link_res.model_dump(),
    }

    mission_id = ctx["task_id"]
    with new_session() as session:
        ids = next_calc_ids(session, mission_id, 6)
        for rid, tool, inputs, outputs, units in (
            (ids[0], "calc.orbit", s4["orbit"], orbit_res.model_dump(), {"orbit": "mixed"}),
            (ids[1], "calc.mass_budget", s4["mass"], mass_res.model_dump(), {"mass": "kg"}),
            (ids[2], "calc.power_budget", s4["power"], power_res.model_dump(), {"power": "W", "energy": "Wh"}),
            (ids[3], "calc.eps", {"p_eol_w": p_eol, "life_years": life_years, **s4["eps"]},
             eps_res.model_dump(), {"power": "W", "area": "m2"}),
            (ids[4], "calc.data_budget", data_input, data_res.model_dump(), {"data": "Gb"}),
            (ids[5], "calc.link_budget", s4["link"], link_res.model_dump(), {"link": "dB"}),
        ):
            session.add(CalculationRecord(
                id=rid, mission_id=mission_id, tool=tool,
                formula_version=FORMULA_VERSIONS[tool],
                inputs=inputs, outputs=outputs, units_map=units,
            ))

        # ---- C1 质量 ----
        upsert_parameter(session, mission_id, id="mass.dry", name="干重", value=mass_res.dry_mass_kg,
                         unit="kg", source_type="calc", source_ref=ids[1], parent="mass")
        upsert_parameter(session, mission_id, id="mass.propellant", name="推进剂质量", value=mass_res.propellant_kg,
                         unit="kg", source_type="calc", source_ref=ids[1], parent="mass")
        upsert_parameter(session, mission_id, id="mass.total", name="整星质量（不含余量）", value=mass_res.total_kg,
                         unit="kg", source_type="calc", source_ref=ids[1], parent="mass",
                         derived_from=["mass.dry", "mass.propellant"])
        upsert_parameter(session, mission_id, id="mass.margin_pct", name="质量余量", value=mass_res.margin_pct * 100,
                         unit="%", source_type="calc", source_ref=ids[1], parent="mass")
        upsert_parameter(session, mission_id, id="mass.total_with_margin", name="整星质量（含余量）",
                         value=mass_res.total_with_margin_kg, unit="kg", source_type="calc",
                         source_ref=ids[1], parent="mass", derived_from=["mass.total", "mass.margin_pct"])

        # ---- C2 功耗 ----
        upsert_parameter(session, mission_id, id="power.p_sun_w", name="光照期功耗", value=power_res.p_sun_w,
                         unit="W", source_type="calc", source_ref=ids[2], parent="power")
        upsert_parameter(session, mission_id, id="power.p_ecl_w", name="阴影期功耗", value=power_res.p_ecl_w,
                         unit="W", source_type="calc", source_ref=ids[2], parent="power")
        upsert_parameter(session, mission_id, id="power.p_avg_w", name="轨道平均功耗", value=power_res.p_avg_w,
                         unit="W", source_type="calc", source_ref=ids[2], parent="power",
                         derived_from=["power.p_sun_w", "power.p_ecl_w"])
        upsert_parameter(session, mission_id, id="power.e_ecl_wh", name="阴影期能耗", value=power_res.e_ecl_wh,
                         unit="Wh", source_type="calc", source_ref=ids[2], parent="power")
        upsert_parameter(session, mission_id, id="power.battery_capacity_wh", name="电池容量需求",
                         value=power_res.battery_capacity_wh, unit="Wh", source_type="calc",
                         source_ref=ids[2], parent="power", derived_from=["power.e_ecl_wh"])

        # ---- C6 太阳翼 ----
        upsert_parameter(session, mission_id, id="power.p_bol_w", name="寿命初期功率", value=eps_res.p_bol_w,
                         unit="W", source_type="calc", source_ref=ids[3], parent="power",
                         derived_from=["power.p_avg_w", "power.e_ecl_wh"])
        upsert_parameter(session, mission_id, id="power.sa.area", name="太阳翼面积", value=eps_res.sa_area_m2,
                         unit="m2", source_type="calc", source_ref=ids[3], parent="power.sa")

        # ---- C3 数据量 ----
        upsert_parameter(session, mission_id, id="data.per_orbit_gb", name="单圈数据量", value=data_res.per_orbit_gb,
                         unit="Gb", source_type="calc", source_ref=ids[4], parent="data")
        upsert_parameter(session, mission_id, id="data.per_day_gb", name="每日数据量", value=data_res.per_day_gb,
                         unit="Gb", source_type="calc", source_ref=ids[4], parent="data",
                         derived_from=["data.per_orbit_gb"])
        upsert_parameter(session, mission_id, id="data.downlink_capacity_gb", name="下行能力",
                         value=data_res.downlink_capacity_gb, unit="Gb", source_type="calc",
                         source_ref=ids[4], parent="data")
        upsert_parameter(session, mission_id, id="data.storage_required_gb", name="存储需求",
                         value=data_res.storage_required_gb, unit="Gb", source_type="calc",
                         source_ref=ids[4], parent="data",
                         derived_from=["data.per_orbit_gb", "data.downlink_capacity_gb"])

        # ---- C5 轨道与覆盖 ----
        upsert_parameter(session, mission_id, id="orbit.period_min", name="轨道周期", value=orbit_res.period_min,
                         unit="min", source_type="calc", source_ref=ids[0], parent="orbit")
        upsert_parameter(session, mission_id, id="orbit.nodal_precession_deg_day", name="交点退行速率",
                         value=orbit_res.nodal_precession_deg_day, unit="deg/day", source_type="calc",
                         source_ref=ids[0], parent="orbit")
        upsert_parameter(session, mission_id, id="orbit.orbits_per_day", name="每日圈次",
                         value=orbit_res.orbits_per_day, unit="1/day", source_type="calc",
                         source_ref=ids[0], parent="orbit")
        upsert_parameter(session, mission_id, id="orbit.windows_per_day", name="每日过境窗口数",
                         value=float(orbit_res.windows_per_day), unit="1/day", source_type="calc",
                         source_ref=ids[0], parent="orbit")
        if orbit_res.revisit_avg_h is not None:
            upsert_parameter(session, mission_id, id="orbit.revisit_avg_h", name="平均重访间隔",
                             value=orbit_res.revisit_avg_h, unit="h", source_type="calc",
                             source_ref=ids[0], parent="orbit")
        if orbit_res.max_gap_h is not None:
            upsert_parameter(session, mission_id, id="orbit.max_gap_h", name="最大覆盖间隔",
                             value=orbit_res.max_gap_h, unit="h", source_type="calc",
                             source_ref=ids[0], parent="orbit")

        # ---- C4 链路 ----
        upsert_parameter(session, mission_id, id="link.fs_loss_db", name="自由空间损耗", value=link_res.fs_loss_db,
                         unit="dB", source_type="calc", source_ref=ids[5], parent="link")
        upsert_parameter(session, mission_id, id="link.ebn0_db", name="比特信噪比", value=link_res.ebn0_db,
                         unit="dB", source_type="calc", source_ref=ids[5], parent="link")
        upsert_parameter(session, mission_id, id="link.margin_db", name="链路余量", value=link_res.margin_db,
                         unit="dB", source_type="calc", source_ref=ids[5], parent="link",
                         derived_from=["link.ebn0_db"])
        session.commit()

    with new_session() as session:
        ctx["params"] = load_params(session, mission_id)

    return {"type": "tool", "output_ref": ids[0], "calc_records": ids}
