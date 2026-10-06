"""C4 链路预算（docs/06 §2 C4；依据 DSN 810-005 方法学，雨衰简化）。"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from app.tools.calc.constants import C_M_S, K_DBW


class LinkInput(BaseModel):
    freq_ghz: float = Field(gt=0)
    slant_km: float = Field(gt=0)
    eirp_dbw: float
    gt_db_per_k: float
    data_rate_kbps: float = Field(gt=0)
    required_ebn0_db: float
    rain_margin_db: float = 0.0
    other_losses_db: float = 0.0
    min_margin_db: float = 3.0


class LinkResult(BaseModel):
    fs_loss_db: float
    ebn0_db: float
    margin_db: float


def link_budget(inp: LinkInput) -> LinkResult:
    wavelength = C_M_S / (inp.freq_ghz * 1e9)
    fs_loss = 20 * math.log10(4 * math.pi * inp.slant_km * 1000.0 / wavelength)
    rate_bps = inp.data_rate_kbps * 1000.0
    ebn0 = (inp.eirp_dbw + inp.gt_db_per_k - fs_loss - inp.rain_margin_db
            - inp.other_losses_db - 10 * math.log10(rate_bps) - K_DBW)
    return LinkResult(
        fs_loss_db=fs_loss,
        ebn0_db=ebn0,
        margin_db=ebn0 - inp.required_ebn0_db,
    )
