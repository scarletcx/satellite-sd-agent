"""V6 敏感性分析（docs/06 §4 V6）：扰动关键输入，观察结论是否翻转。

当前覆盖：
(a) 质量分项 +10% → 是否仍满足整星质量上限；
(b) 链路额外损耗 +2 dB → 余量是否跌破门限。
"""
from __future__ import annotations

from copy import deepcopy

from app.validation.recompute import recompute

MASS_GROWTH = 0.10
EXTRA_LOSS_DB = 2.0


def _find(records: list[dict], tool: str) -> dict | None:
    return next((record for record in records if record["tool"] == tool), None)


def v6_sensitivity(records: list[dict], constraints: dict) -> list[dict]:
    findings: list[dict] = []

    mass_record = _find(records, "calc.mass_budget")
    limit = (constraints or {}).get("mass_limit_kg")
    if mass_record and limit:
        base = recompute("calc.mass_budget", mass_record["inputs"])["total_with_margin_kg"]
        perturbed = deepcopy(mass_record["inputs"])
        for item in perturbed["items"]:
            item["mass_kg"] = float(item["mass_kg"]) * (1 + MASS_GROWTH)
        grown = recompute("calc.mass_budget", perturbed)["total_with_margin_kg"]
        if base <= limit < grown:
            findings.append({
                "rule_id": "V6", "status": "warn", "param_id": "mass.total_with_margin",
                "message": (f"敏感：分项质量 +10% 后预计 {grown:.1f} kg，将超出上限 {limit:.1f} kg"
                            f"（当前 {base:.1f} kg）"),
                "evidence": {"growth_pct": MASS_GROWTH * 100, "base": base,
                             "perturbed": grown, "limit": limit},
            })
        else:
            findings.append({
                "rule_id": "V6", "status": "pass", "param_id": "mass.total_with_margin",
                "message": f"敏感性：分项质量 +10% 后 {grown:.1f} kg，仍在上限 {limit:.1f} kg 内",
                "evidence": {"growth_pct": MASS_GROWTH * 100, "perturbed": grown, "limit": limit},
            })

    link_record = _find(records, "calc.link_budget")
    if link_record:
        base = recompute("calc.link_budget", link_record["inputs"])["margin_db"]
        min_margin = float(link_record["inputs"].get("min_margin_db", 3.0))
        perturbed = deepcopy(link_record["inputs"])
        perturbed["other_losses_db"] = float(perturbed.get("other_losses_db", 0.0)) + EXTRA_LOSS_DB
        reduced = recompute("calc.link_budget", perturbed)["margin_db"]
        if reduced < min_margin:
            findings.append({
                "rule_id": "V6", "status": "warn", "param_id": "link.margin_db",
                "message": (f"敏感：额外 {EXTRA_LOSS_DB:.0f} dB 损耗后链路余量 {reduced:.2f} dB "
                            f"跌破门限 {min_margin:.1f} dB（当前 {base:.2f} dB）"),
                "evidence": {"extra_loss_db": EXTRA_LOSS_DB, "base": base,
                             "perturbed": reduced, "min_margin": min_margin},
            })
        else:
            findings.append({
                "rule_id": "V6", "status": "pass", "param_id": "link.margin_db",
                "message": f"敏感性：额外 {EXTRA_LOSS_DB:.0f} dB 损耗后余量 {reduced:.2f} dB，仍在门限内",
                "evidence": {"extra_loss_db": EXTRA_LOSS_DB, "perturbed": reduced},
            })

    return findings
