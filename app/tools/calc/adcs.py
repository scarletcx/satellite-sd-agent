"""C7 姿控粗算（docs/06 §2 C7）：光压扰动力矩 → 轮组角动量需求 → 磁力矩器卸载能力。

任务级粗算模型（公开公式，量级估算）：
- 太阳光压扰动力矩：T_sp = P0 · A_sa · (1 + cps) · L_arm，P0 = 4.56e-6 N/m²（1 AU 辐射压）
- 其他扰动（重力梯度 / 气动 / 磁）以放大系数 k_other 计入：T_total = k_other · T_sp
- 反作用轮角动量需求：H = margin · T_total · T_orbit / π（半周期双向累积的工程近似）
- 磁力矩器卸载能力：M = T_total / B_min（B_min = 2.5e-5 T，低轨低值）
仅用于方案阶段量级估算，详细控制律与裕度需姿控专业设计确认。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

RADIATION_PRESSURE_N_M2 = 4.56e-6   # 1 AU 太阳辐射压
DEFAULT_CPS = 0.3                   # 太阳翼反射系数（典型值）
DEFAULT_K_OTHER = 2.0               # 其他扰动放大系数
DEFAULT_MARGIN = 1.5                # 角动量安全系数
MIN_MAGNETIC_FIELD_T = 2.5e-5       # 低轨磁感应强度低值


class AdcsInput(BaseModel):
    sa_area_m2: float = Field(gt=0, description="太阳翼面积（来自 C6）")
    mass_kg: float = Field(gt=0, description="整星质量（含余量）")
    arm_m: float = Field(gt=0, description="光压力臂（取包络半长）")
    t_orbit_min: float = Field(gt=0, description="轨道周期（来自 C5）")
    cps: float = Field(default=DEFAULT_CPS, ge=0, le=1)
    k_other: float = Field(default=DEFAULT_K_OTHER, ge=1, le=5)
    margin: float = Field(default=DEFAULT_MARGIN, ge=1, le=3)


class AdcsResult(BaseModel):
    t_sp_unm: float          # 光压扰动力矩，µN·m
    t_total_unm: float       # 综合扰动力矩，µN·m
    h_required_nms: float    # 轮组角动量需求，N·m·s
    mtq_dipole_am2: float    # 磁力矩器磁矩需求，A·m²


def adcs_estimate(inp: AdcsInput) -> AdcsResult:
    t_sp_nm = RADIATION_PRESSURE_N_M2 * inp.sa_area_m2 * (1 + inp.cps) * inp.arm_m
    t_total_nm = inp.k_other * t_sp_nm
    h_required = inp.margin * t_total_nm * (inp.t_orbit_min * 60.0) / 3.141592653589793
    dipole = t_total_nm / MIN_MAGNETIC_FIELD_T
    return AdcsResult(
        t_sp_unm=t_sp_nm * 1e6,
        t_total_unm=t_total_nm * 1e6,
        h_required_nms=h_required,
        mtq_dipole_am2=dipole,
    )
