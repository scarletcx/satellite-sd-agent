"""V5 历史型号对比（docs/06 §4 V5）：与公开统计分布比对。

参考分布来自 UCS Satellite Database（LEO、10~500 kg 小卫星）的公开统计，
由 `scripts/build_reference.py` 生成到 `app/data/reference_ranges.json`；
文件缺失时本规则自动跳过。
"""
from __future__ import annotations

import json

from app.config import BASE_DIR

REFERENCE_PATH = BASE_DIR / "app" / "data" / "reference_ranges.json"

# (参数 id, 参考区间键, 展示名)
CHECKS = (
    ("mass.total_with_margin", "mass_kg", "整星质量"),
    ("power.p_avg_w", "power_w", "轨道平均功耗"),
)


def _load_reference() -> dict | None:
    if not REFERENCE_PATH.exists():
        return None
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def v5_history(params: dict[str, float], reference: dict | None = None) -> list[dict]:
    """params 为 id→value 映射；落在 [P10, P90] 之外 → warn（只需复核，不阻塞）。"""
    reference = reference if reference is not None else _load_reference()
    if not reference:
        return []

    findings: list[dict] = []
    checked: list[str] = []
    for param_id, key, label in CHECKS:
        value = params.get(param_id)
        ranges = (reference.get("ranges") or {}).get(key)
        if value is None or not ranges:
            continue
        checked.append(label)
        if value < ranges["p10"]:
            findings.append({
                "rule_id": "V5", "status": "warn", "param_id": param_id,
                "message": f"{label} {value:.1f} 低于同类卫星 P10（{ranges['p10']:.1f}），请复核",
                "evidence": {"value": value, "p10": ranges["p10"], "p90": ranges["p90"],
                             "source": reference.get("source")},
            })
        elif value > ranges["p90"]:
            findings.append({
                "rule_id": "V5", "status": "warn", "param_id": param_id,
                "message": f"{label} {value:.1f} 高于同类卫星 P90（{ranges['p90']:.1f}），请复核",
                "evidence": {"value": value, "p10": ranges["p10"], "p90": ranges["p90"],
                             "source": reference.get("source")},
            })
    if not findings and checked:
        findings.append({
            "rule_id": "V5", "status": "pass", "param_id": None,
            "message": "、".join(checked) + f" 落在同类卫星 P10~P90 区间内（参考 {reference.get('source')}）",
            "evidence": {"sample_n": reference.get("sample_n")},
        })
    return findings
