"""预算计算 C1~C3（公式与边界见 docs/06 §2；输入模型与 specs/schemas/tools 对应）。

约定：函数输入经 pydantic 校验（缺项 / 非法即拒绝）；输出为全精度数值，展示时再舍入。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------- C1 质量预算


class MassItem(BaseModel):
    name: str
    mass_kg: float = Field(gt=0)
    margin: float | None = None
    source_ref: str


class MarginPolicy(BaseModel):
    phase: Literal["方案", "初样"] = "方案"
    pct: float = Field(ge=0, le=1)


class MassInput(BaseModel):
    items: list[MassItem] = Field(min_length=1)
    propellant_kg: float = Field(ge=0)
    margin_policy: MarginPolicy


class MassResult(BaseModel):
    dry_mass_kg: float
    propellant_kg: float
    total_kg: float
    margin_pct: float
    margin_mass_kg: float
    total_with_margin_kg: float


def mass_budget(inp: MassInput) -> MassResult:
    dry = sum(item.mass_kg for item in inp.items)
    total = dry + inp.propellant_kg
    margin_mass = total * inp.margin_policy.pct
    return MassResult(
        dry_mass_kg=dry,
        propellant_kg=inp.propellant_kg,
        total_kg=total,
        margin_pct=inp.margin_policy.pct,
        margin_mass_kg=margin_mass,
        total_with_margin_kg=total + margin_mass,
    )


# ---------------------------------------------------------------- C2 功耗预算


class PowerLoad(BaseModel):
    name: str
    phase: Literal["sun", "ecl", "both"]
    power_w: float = Field(ge=0)
    duty_pct: float = Field(ge=0, le=100)


class PowerInput(BaseModel):
    loads: list[PowerLoad] = Field(min_length=1)
    t_orbit_min: float = Field(gt=0)
    t_ecl_min: float = Field(ge=0)
    dod: float = Field(gt=0, le=1)
    eta_out: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _check_eclipse(self) -> "PowerInput":
        if self.t_ecl_min >= self.t_orbit_min:
            raise ValueError("T_ecl_min 必须小于 T_orbit_min")
        return self


class PowerResult(BaseModel):
    p_sun_w: float
    p_ecl_w: float
    p_avg_w: float
    e_ecl_wh: float
    battery_capacity_wh: float


def power_budget(inp: PowerInput) -> PowerResult:
    def phase_power(target: str) -> float:
        total = 0.0
        for load in inp.loads:
            if load.phase in (target, "both"):
                total += load.power_w * load.duty_pct / 100.0
        return total

    p_sun = phase_power("sun")
    p_ecl = phase_power("ecl")
    t_sun = inp.t_orbit_min - inp.t_ecl_min
    p_avg = (p_sun * t_sun + p_ecl * inp.t_ecl_min) / inp.t_orbit_min
    e_ecl = p_ecl * inp.t_ecl_min / 60.0  # Wh
    battery = e_ecl / (inp.dod * inp.eta_out)
    return PowerResult(
        p_sun_w=p_sun,
        p_ecl_w=p_ecl,
        p_avg_w=p_avg,
        e_ecl_wh=e_ecl,
        battery_capacity_wh=battery,
    )


# ------------------------------------------------------------ C3 数据量预算


class DataInput(BaseModel):
    rate_mbps: float = Field(gt=0, description="载荷数据率")
    imaging_min_per_orbit: float = Field(ge=0)
    compression_ratio: float = Field(ge=1)
    downlink_rate_mbps: float = Field(gt=0)
    downlink_window_min_per_day: float = Field(ge=0)
    orbits_per_day: float = Field(gt=0)
    storage_cycles: int = Field(default=2, ge=1)


class DataResult(BaseModel):
    per_orbit_gb: float
    per_day_gb: float
    downlink_capacity_gb: float
    storage_required_gb: float


def data_budget(inp: DataInput) -> DataResult:
    # 十进制换算：1 GB = 8000 Mb
    per_orbit = inp.rate_mbps * inp.imaging_min_per_orbit * 60.0 / (8 * 1000 * inp.compression_ratio)
    per_day = per_orbit * inp.orbits_per_day
    downlink = inp.downlink_rate_mbps * inp.downlink_window_min_per_day * 60.0 / 8000.0
    unres = max(0.0, per_day - downlink)
    storage = max(inp.storage_cycles * per_orbit, unres)
    return DataResult(
        per_orbit_gb=per_orbit,
        per_day_gb=per_day,
        downlink_capacity_gb=downlink,
        storage_required_gb=storage,
    )
