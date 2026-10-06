"""ADV-01 演示：篡改参数使其失去计算依据 → 校验拦截（docs/11 §4 / docs/15 §3）。

流程：新建任务并跑通 → 篡改 mass.total_with_margin（52.0 kg + 伪造 source_ref）
→ 重跑校验（S6）→ 预期 V1 block、任务挂起 awaiting_gate、导出被系统阻止。
每次运行都会新建任务，可重复执行。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import init_db, new_session  # noqa: E402
from app.models import AuditLog, DesignParameter, Mission, ValidationResult  # noqa: E402
from app.orchestrator import engine  # noqa: E402
from app.orchestrator.ids import next_mission_id  # noqa: E402


def _create_mission() -> str:
    with new_session() as session:
        task_id = next_mission_id(session)
        session.add(Mission(
            id=task_id,
            goal="设计一颗 500km SSO 光学遥感小卫星",
            constraints={"orbit_type": "SSO", "altitude_km": 500,
                         "lifetime_years": 3, "mass_limit_kg": 80},
            status="queued",
        ))
        session.commit()
    return task_id


async def main() -> int:
    init_db()
    task_id = _create_mission()

    print(f"[1/4] 正常运行任务 {task_id} …")
    await engine.run_mission(task_id)
    with new_session() as session:
        mission = session.get(Mission, task_id)
        param = session.get(DesignParameter, ("mass.total_with_margin", task_id))
        if mission.status != "succeeded" or param is None:
            print(f"      ✗ 预期 succeeded，实际 {mission.status}")
            return 1
        original = param.value
        print(f"      ✓ 完成：mass.total_with_margin = {original:.1f} kg（来源 {param.source_ref}）")

        print("[2/4] 注入异常：数值改为 52.0 kg，来源指向不存在的计算记录 …")
        param.value = 52.0
        param.source_ref = "calc-19990101-9999"
        session.add(AuditLog(
            entity="design_parameter", entity_id=param.id, field="value",
            before={"value": original}, after={"value": 52.0},
            who="demo:adv", why="ADV-01 注入（无计算过程数字）",
        ))
        session.commit()

    print("[3/4] 重新校验（S6）…")
    await engine.run_mission(task_id, start_from="S6")

    with new_session() as session:
        mission = session.get(Mission, task_id)
        blocks = (session.query(ValidationResult)
                  .filter(ValidationResult.mission_id == task_id,
                          ValidationResult.status == "block").all())
        print(f"      状态：{mission.status}；block 结论 {len(blocks)} 条")
        for row in blocks[:3]:
            print(f"        - [{row.rule_id}] {row.param_id}: {row.message}")

    if mission.status == "awaiting_gate" and blocks:
        print("[4/4] ✓ 拦截生效：无计算依据的数字未通过校验，任务挂起，导出被系统阻止（A10 将返回 409）。")
        print("      恢复方式：把数值/来源改回真实记录后调用 A9 重新校验，或经 A8 人工处置并留审计。")
        return 0
    print("[4/4] ✗ 未按预期拦截")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
