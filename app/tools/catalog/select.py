"""选型规则：按类别做「满足指标约束 + 代价最小」的确定性筛选与打分。

每类给出 1~2 个候选，附选择理由（含关键数字），供文档第 10 章与界面展示。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import BASE_DIR

CATALOG_PATH = BASE_DIR / "data" / "parts_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    data = json.loads(Path(CATALOG_PATH).read_text(encoding="utf-8"))
    return list(data.get("items", []))


def _pick(items: list[dict], category: str) -> list[dict]:
    return [item for item in items if item.get("category") == category]


def _candidate(item: dict, score: float, reason: str) -> dict:
    return {
        "category": item["category"],
        "name": item["name"],
        "vendor": item.get("vendor", ""),
        "params": dict(item.get("params", {})),
        "score": round(max(0.0, min(100.0, score)), 1),
        "reason": reason,
        "source_ref": item.get("source_ref", ""),
        "catalog_id": item["id"],
    }


def _battery(items: list[dict], params: dict) -> list[dict]:
    required_wh = float(params.get("power.battery_capacity_wh") or 0)
    if required_wh <= 0:
        return []
    ranked = []
    for item in _pick(items, "battery"):
        wh_per_kg = float(item["params"]["wh_per_kg"])
        mass_kg = required_wh / wh_per_kg
        ranked.append((mass_kg, item))
    ranked.sort(key=lambda pair: pair[0])
    results = []
    for mass_kg, item in ranked[:2]:
        score = 100.0 * (1 - mass_kg / 10.0)  # 10 kg 为电池组质量参考上限
        results.append(_candidate(
            item, score,
            f"容量需求 {required_wh:.1f} Wh → 按 {item['params']['wh_per_kg']} Wh/kg 估算约 {mass_kg:.2f} kg"))
    return results


def _solar_cell(items: list[dict], inputs: dict) -> list[dict]:
    required_eff = float((inputs.get("eps") or {}).get("cell_efficiency") or 0)
    cells = _pick(items, "solar_cell")
    if not cells:
        return []
    meets = [item for item in cells if float(item["params"]["efficiency"]) >= required_eff]
    pool = meets or [max(cells, key=lambda item: item["params"]["efficiency"])]
    pool.sort(key=lambda item: float(item["params"]["efficiency"]))
    results = []
    for item in pool[:2 if meets else 1]:
        efficiency = float(item["params"]["efficiency"])
        score = 100.0 if meets else 40.0
        note = (f"满足输入假设效率 {required_eff:.0%}" if meets
                else f"库内无满足 {required_eff:.0%} 的电池，最高为 {efficiency:.0%}（需总体复核假设）")
        results.append(_candidate(item, score,
                                  f"{note}；候选效率 {efficiency:.0%}"))
    return results


def _transponder(items: list[dict]) -> list[dict]:
    ranked = sorted(_pick(items, "transponder"), key=lambda item: float(item["params"]["mass_kg"]))
    return [
        _candidate(item, 100.0 - float(item["params"]["mass_kg"]) * 5,
                   f"S 频段测控体制；质量 {item['params']['mass_kg']} kg，功耗 {item['params']['power_w']} W")
        for item in ranked[:2]
    ]


def _transmitter(items: list[dict], inputs: dict) -> list[dict]:
    required_mbps = float((inputs.get("data") or {}).get("downlink_rate_mbps") or 0)
    pool = [item for item in _pick(items, "transmitter")
            if float(item["params"].get("data_rate_mbps", 0)) >= required_mbps]
    if not pool:
        pool = _pick(items, "transmitter")
    pool.sort(key=lambda item: float(item["params"]["mass_kg"]))
    return [
        _candidate(item, 100.0 - float(item["params"]["mass_kg"]) * 5,
                   (f"数传速率需求 {required_mbps:.0f} Mbps；候选能力 "
                    f"{item['params'].get('data_rate_mbps', 0):.0f} Mbps，质量 {item['params']['mass_kg']} kg"))
        for item in pool[:2]
    ]


def _obc(items: list[dict]) -> list[dict]:
    ranked = sorted(_pick(items, "obc"), key=lambda item: float(item["params"]["mass_kg"]))
    return [
        _candidate(item, 100.0 - float(item["params"]["mass_kg"]) * 10,
                   f"星务计算机；质量 {item['params']['mass_kg']} kg，功耗 {item['params']['power_w']} W")
        for item in ranked[:2]
    ]


def _adcs(items: list[dict], params: dict) -> list[dict]:
    """姿控执行机构：按 C7 粗算的角动量需求与磁矩需求筛选。"""
    requirement = float(params.get("adcs.h_required_nms") or 0)  # N·m·s
    results: list[dict] = []
    if requirement > 0:
        wheels = [item for item in _pick(items, "reaction_wheel")
                  if float(item["params"]["momentum_nms"]) >= requirement]
        wheels.sort(key=lambda item: float(item["params"]["momentum_nms"]))
        for item in wheels[:2]:
            momentum = float(item["params"]["momentum_nms"])
            score = 100.0 * (requirement / momentum)  # 余量越大分越低（够用即好）
            results.append(_candidate(
                item, score,
                (f"角动量需求 ≥{requirement * 1000:.1f} mN·m·s；候选 {momentum * 1000:.0f} mN·m·s，"
                 f"质量 {item['params']['mass_kg']} kg")))
    dipole = float(params.get("adcs.mtq_dipole_am2") or 0)
    if dipole > 0:
        mtqs = [item for item in _pick(items, "magnetorquer")
                if float(item["params"]["dipole_am2"]) >= dipole]
        mtqs.sort(key=lambda item: float(item["params"]["dipole_am2"]))
        for item in mtqs[:1]:
            results.append(_candidate(
                item, 100.0,
                (f"磁矩需求 ≥{dipole:.2f} A·m²；候选 {item['params']['dipole_am2']} A·m²，"
                 f"质量 {item['params']['mass_kg']} kg")))
    return results


def select_candidates(params: dict, inputs: dict) -> list[dict]:
    """params：IR 参数值字典；inputs：S4 分组设计输入。"""
    items = load_catalog()
    return [
        *_battery(items, params),
        *_solar_cell(items, inputs),
        *_transponder(items),
        *_transmitter(items, inputs),
        *_obc(items),
        *_adcs(items, params),
    ]
