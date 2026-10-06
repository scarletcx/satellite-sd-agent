"""单位枚举与校验（docs/03 §4）。换算集中于此，禁止散落。"""
from __future__ import annotations

UNIT_ENUM: tuple[str, ...] = (
    "kg", "g", "m", "mm", "km", "m2",
    "W", "kW", "Wh", "V", "Ah",
    "s", "min", "h", "day", "year",
    "bit", "Gb", "Gb/day", "Mbps",
    "dB", "dBW", "dBi", "dB/K", "Hz", "GHz",
    "N", "N·m", "N·m·s", "kg·m2",
    "deg", "deg/day", "1/day", "%", "ppm",
)


class UnitError(ValueError):
    """单位不在枚举内。"""


def require_unit(unit: str) -> str:
    if unit not in UNIT_ENUM:
        raise UnitError(f"未知单位：{unit!r}（允许值：{UNIT_ENUM}）")
    return unit
