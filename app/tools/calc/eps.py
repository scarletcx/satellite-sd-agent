"""C6 太阳翼尺寸（docs/06 §2 C6；EOL/BOL 衰减 + 效率链）。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.tools.calc.constants import E0_W_M2


class EpsInput(BaseModel):
    p_eol_w: float = Field(gt=0, description="寿命末期所需功率（含充电功率）")
    life_years: float = Field(gt=0, le=20)
    degradation_per_year: float = Field(gt=0, lt=1, description="年衰减率")
    cell_efficiency: float = Field(gt=0, le=1)
    packing_factor: float = Field(gt=0, le=1)
    sun_angle_cos: float = Field(default=0.9, gt=0, le=1)
    margin_pct: float = Field(default=0.1, ge=0, le=1)


class EpsResult(BaseModel):
    p_bol_w: float
    sa_area_m2: float


def eps_sizing(inp: EpsInput) -> EpsResult:
    p_bol = inp.p_eol_w / (1 - inp.degradation_per_year) ** inp.life_years
    area = (p_bol / (E0_W_M2 * inp.cell_efficiency * inp.packing_factor * inp.sun_angle_cos)
            * (1 + inp.margin_pct))
    return EpsResult(p_bol_w=p_bol, sa_area_m2=area)
