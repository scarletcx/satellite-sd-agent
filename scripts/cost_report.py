"""任务成本报告：汇总 trace 中的 llm_call 记录（docs/12 §4）。

用法：make cost-report TASK=<task_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tracing import read_trace  # noqa: E402


def main(task_id: str) -> int:
    if not task_id:
        print("用法：python scripts/cost_report.py <task_id>（或 make cost-report TASK=<task_id>）")
        return 2

    calls = [event for event in read_trace(task_id) if event.get("type") == "llm_call"]
    total = sum(float(event.get("cost_estimate_cny") or 0.0) for event in calls)
    print(f"任务 {task_id}：llm_call {len(calls)} 次，成本合计 ¥{total:.4f}")
    for event in calls:
        tokens = event.get("tokens") or {}
        repair = event.get("repair_attempts") or 0
        print(f"  {event.get('step')}  {event.get('provider')}/{event.get('model')}  "
              f"in={tokens.get('in')} out={tokens.get('out')}  ¥{float(event.get('cost_estimate_cny') or 0):.4f}"
              + (f"  修复重试 {repair} 次" if repair else ""))
    if not calls:
        print("  （无记录：桩模式不产生成本）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
