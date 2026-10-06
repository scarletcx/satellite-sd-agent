"""C5 轨道与覆盖（自研简化模型：圆轨道 + J2 交点退行 + 球面几何可见性）。

适用范围：任务级方案估算（docs/06 §2 C5 / ADR-0004），不做高精度定轨与精密覆盖；
交叉验证（与开源库对拍）为后续项。
"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from app.tools.calc.constants import J2, MU_EARTH_KM3_S2, RE_KM

SIDEREAL_DAY_S = 86164.0905
SUN_MEAN_MOTION_DEG_DAY = 0.9856  # 太阳视运动平均角速度（SSO 判据）

EARTH_ROTATION_DEG_S = 360.0 / SIDEREAL_DAY_S


class OrbitInput(BaseModel):
    alt_km: float = Field(ge=200, le=36000)
    inc_deg: float = Field(ge=0, le=180)
    station_lat: float = Field(ge=-90, le=90)
    station_lon: float = Field(ge=-180, le=180)
    min_elevation_deg: float = Field(default=5, ge=0, le=90)
    sample_step_s: int = Field(default=30, ge=5, le=120)


class OrbitResult(BaseModel):
    period_min: float
    nodal_precession_deg_day: float
    sso_ok: bool
    orbits_per_day: float
    windows_per_day: int
    revisit_avg_h: float | None
    max_gap_h: float | None


def orbit_coverage(inp: OrbitInput) -> OrbitResult:
    semi_major = RE_KM + inp.alt_km
    n = math.sqrt(MU_EARTH_KM3_S2 / semi_major**3)          # rad/s
    period_s = 2 * math.pi / n
    inclination = math.radians(inp.inc_deg)

    # J2 交点退行（rad/s → deg/day）
    raan_dot = -1.5 * J2 * n * (RE_KM / semi_major) ** 2 * math.cos(inclination)
    raan_dot_deg_day = math.degrees(raan_dot) * 86400.0
    sso_ok = abs(raan_dot_deg_day - SUN_MEAN_MOTION_DEG_DAY) < 0.05
    orbits_per_day = 86400.0 / period_s

    # 站点 ECEF 坐标
    lat = math.radians(inp.station_lat)
    lon = math.radians(inp.station_lon)
    station = (RE_KM * math.cos(lat) * math.cos(lon),
               RE_KM * math.cos(lat) * math.sin(lon),
               RE_KM * math.sin(lat))
    min_elevation = math.radians(inp.min_elevation_deg)

    def elevation_deg(t_s: float) -> float:
        """圆轨道位置（RAAN0=0 任意相位）→ ECEF（忽略 GMST 初值）→ 仰角。"""
        u = n * t_s
        raan = raan_dot * t_s
        cos_u, sin_u = math.cos(u), math.sin(u)
        x = semi_major * (math.cos(raan) * cos_u - math.sin(raan) * sin_u * math.cos(inclination))
        y = semi_major * (math.sin(raan) * cos_u + math.cos(raan) * sin_u * math.cos(inclination))
        z = semi_major * (sin_u * math.sin(inclination))
        theta = math.radians(EARTH_ROTATION_DEG_S) * t_s
        ct, st = math.cos(-theta), math.sin(-theta)
        x_e, y_e, z_e = x * ct - y * st, x * st + y * ct, z
        # 视线矢量 vs 站心天顶
        lx, ly, lz = x_e - station[0], y_e - station[1], z_e - station[2]
        cos_zenith = ((lx * station[0] + ly * station[1] + lz * station[2])
                      / (math.sqrt(lx * lx + ly * ly + lz * lz)
                         * math.sqrt(station[0] ** 2 + station[1] ** 2 + station[2] ** 2)))
        zenith = math.acos(max(-1.0, min(1.0, cos_zenith)))
        return 90.0 - math.degrees(zenith)

    # 一日采样：统计可见窗口（过境）
    windows: list[tuple[float, float]] = []
    inside = False
    start = 0.0
    step = inp.sample_step_s
    horizon = 86400.0
    t = 0.0
    while t <= horizon:
        visible = elevation_deg(t) >= inp.min_elevation_deg
        if visible and not inside:
            inside, start = True, t
        elif not visible and inside:
            windows.append((start, t))
            inside = False
        t += step
    if inside:
        windows.append((start, horizon))

    revisit_avg_h: float | None = None
    max_gap_h: float | None = None
    if len(windows) >= 2:
        gaps = [windows[i + 1][0] - windows[i][0] for i in range(len(windows) - 1)]
        revisit_avg_h = sum(gaps) / len(gaps) / 3600.0
        max_gap_h = max(gaps) / 3600.0

    return OrbitResult(
        period_min=period_s / 60.0,
        nodal_precession_deg_day=raan_dot_deg_day,
        sso_ok=sso_ok,
        orbits_per_day=orbits_per_day,
        windows_per_day=len(windows),
        revisit_avg_h=revisit_avg_h,
        max_gap_h=max_gap_h,
    )
