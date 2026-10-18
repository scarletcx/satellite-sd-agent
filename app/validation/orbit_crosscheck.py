"""C5 轨道交叉验证（docs/06 §2 C5、ADR-0004）：用 skyfield（SGP4）独立复算。

与自研解析模型（`app/tools/calc/orbit.py`）相互独立：SGP4 是成熟开源实现，
本模块用它复算轨道周期与交点退行率，用于发现解析模型的公式实现错误。

方法：
- 由任务轨道要素构造 OMM（偏心率为 0 的圆轨道近似），交给 skyfield 传播；
- 以二分法求上升交点时刻，取交点在惯性系中的经度序列；
- 解卷绕后做最小二乘拟合，得到退行率（逐圈求和对采样相位敏感，拟合后稳定）；
- 与计算记录比对：周期容差 0.5%，退行率容差 2%（实测残差 ≈0.06% / ≈0.2%，
  其余差异来自 SGP4 均值根数与解析 J2 模型的模型差异）。

离线可用（skyfield 自带时间尺度数据）；未安装 skyfield 时跳过并给 warn。
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

MU_EARTH_KM3_S2 = 398600.4418
RE_KM = 6378.137
EPOCH_YMD = (2026, 10, 6, 0, 0, 0)      # 固定历元，保证可复现
DEFAULT_DAYS = 2.0
DEFAULT_STEP_S = 60.0
BISECTION_ITER = 40                     # 交点时刻精度 < 1 ms
PERIOD_TOLERANCE_PCT = 0.5
DRIFT_TOLERANCE_PCT = 2.0


def skyfield_available() -> bool:
    if os.getenv("ORBIT_CROSSCHECK", "1") in ("0", "false", "False"):
        return False
    try:
        import skyfield  # noqa: F401
        return True
    except ImportError:
        return False


@lru_cache(maxsize=32)   # 结果确定性，按要素缓存（重复校验/重算不再重跑 SGP4）
def crosscheck_orbit(alt_km: float, inc_deg: float,
                     days: float = DEFAULT_DAYS, step_s: float = DEFAULT_STEP_S) -> dict:
    """用 SGP4 独立复算轨道周期（min）与交点退行率（deg/day）。"""
    from skyfield.api import EarthSatellite, load

    timescale = load.timescale()
    semi_major = RE_KM + float(alt_km)
    rev_per_day = math.sqrt(MU_EARTH_KM3_S2 / semi_major**3) * 86400.0 / (2 * math.pi)
    omm = {
        "OBJECT_NAME": "CROSSCHECK", "OBJECT_ID": "2026-001A",
        "EPOCH": "%04d-%02d-%02dT%02d:%02d:%02d.000000" % EPOCH_YMD,
        "MEAN_MOTION": rev_per_day, "ECCENTRICITY": 0.0001,
        "INCLINATION": float(inc_deg), "RA_OF_ASC_NODE": 0.0,
        "ARG_OF_PERICENTER": 0.0, "MEAN_ANOMALY": 0.0,
        "EPHEMERIS_TYPE": 0, "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": 99999, "ELEMENT_SET_NO": 999, "REV_AT_EPOCH": 0,
        "BSTAR": 0.0, "MEAN_MOTION_DOT": 0.0, "MEAN_MOTION_DDOT": 0.0,
    }
    satellite = EarthSatellite.from_omm(timescale, omm)
    t0 = timescale.utc(*EPOCH_YMD).tt

    def position(jd: float):
        return satellite.at(timescale.tt_jd(jd)).position.km

    def z_of(jd: float) -> float:
        return position(jd)[2]

    crossings: list[tuple[float, float]] = []
    previous: tuple[float, float] | None = None
    steps = int(days * 86400.0 / step_s)
    for index in range(steps + 1):
        jd = t0 + index * step_s / 86400.0
        z = z_of(jd)
        if previous is not None and previous[1] <= 0 < z:
            low, high = previous[0], jd
            for _ in range(BISECTION_ITER):
                mid = (low + high) / 2.0
                if z_of(mid) <= 0:
                    low = mid
                else:
                    high = mid
            crossing_jd = (low + high) / 2.0
            x, y, _ = position(crossing_jd)
            crossings.append((crossing_jd, math.degrees(math.atan2(y, x))))
        previous = (jd, z)

    if len(crossings) < 3:
        raise RuntimeError("交点样本不足，无法完成轨道交叉验证")

    times = [item[0] for item in crossings]
    angles = [item[1] for item in crossings]
    unwrapped = [angles[0]]
    for first, second in zip(angles, angles[1:]):
        unwrapped.append(unwrapped[-1] + ((second - first + 180.0) % 360.0 - 180.0))

    # 最小二乘线性拟合（以天为单位）
    x = [value - times[0] for value in times]
    count = len(x)
    sum_x, sum_y = sum(x), sum(unwrapped)
    sum_xx = sum(value * value for value in x)
    sum_xy = sum(value * y for value, y in zip(x, unwrapped))
    denominator = count * sum_xx - sum_x * sum_x
    drift_deg_per_day = (count * sum_xy - sum_x * sum_y) / denominator

    period_min = (times[-1] - times[0]) * 1440.0 / (count - 1)
    return {
        "period_min": period_min,
        "nodal_precession_deg_day": drift_deg_per_day,
        "crossings": count,
        "days": days,
    }


def _diff_pct(recorded: float, reference: float) -> float:
    return abs(recorded - reference) / max(abs(reference), 1e-9) * 100.0


def v2_orbit_crosscheck(records: list[dict]) -> list[dict]:
    """对 calc.orbit 记录做第三方库交叉验证；未安装库时给出 warn。"""
    orbit_records = [item for item in records if item.get("tool") == "calc.orbit"]
    if not orbit_records:
        return []
    if not skyfield_available():
        return [{
            "rule_id": "V2", "status": "warn", "param_id": "orbit.period_min",
            "message": "轨道交叉验证库（skyfield）未安装或已禁用，本次跳过第三方复算",
            "evidence": {"rule": "C5-crosscheck", "skipped": True},
        }]

    findings: list[dict] = []
    for record in orbit_records:
        inputs = record.get("inputs") or {}
        outputs = record.get("outputs") or {}
        try:
            reference = crosscheck_orbit(float(inputs["alt_km"]), float(inputs["inc_deg"]))
        except Exception as exc:  # noqa: BLE001 —— 交叉验证失败不阻塞，但必须可见
            findings.append({
                "rule_id": "V2", "status": "warn", "param_id": "orbit.period_min",
                "message": f"轨道交叉验证未完成：{exc}",
                "evidence": {"rule": "C5-crosscheck", "error": str(exc)},
            })
            continue

        period_diff = _diff_pct(float(outputs.get("period_min", 0.0)), reference["period_min"])
        drift_recorded = float(outputs.get("nodal_precession_deg_day", 0.0))
        drift_diff = _diff_pct(drift_recorded, reference["nodal_precession_deg_day"])
        status = "pass" if (period_diff <= PERIOD_TOLERANCE_PCT
                            and drift_diff <= DRIFT_TOLERANCE_PCT) else "block"
        message = (
            f"轨道交叉验证（SGP4/{reference['crossings']} 个交点样本）："
            f"周期 {outputs.get('period_min', 0.0):.4f} vs {reference['period_min']:.4f} min（{period_diff:.3f}%）；"
            f"交点退行 {drift_recorded:.5f} vs {reference['nodal_precession_deg_day']:.5f} deg/day（{drift_diff:.3f}%）"
        )
        findings.append({
            "rule_id": "V2", "status": status, "param_id": "orbit.period_min",
            "message": message,
            "evidence": {
                "rule": "C5-crosscheck", "record_id": record.get("id"),
                "period_diff_pct": period_diff, "drift_diff_pct": drift_diff,
                "tolerances": {"period_pct": PERIOD_TOLERANCE_PCT, "drift_pct": DRIFT_TOLERANCE_PCT},
                "reference": {key: reference[key] for key in
                              ("period_min", "nodal_precession_deg_day", "crossings", "days")},
            },
        })
    return findings
