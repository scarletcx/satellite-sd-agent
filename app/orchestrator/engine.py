"""编排状态机（docs/05 §1~§2）。

S1~S9 顺序执行；S6 出现 block 时挂起门禁（awaiting_gate），
人工评审通过后由 continue_mission() 从 S7 断点恢复。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from app.config import settings
from app.db import new_session
from app.models import Mission, ReviewGate
from app.orchestrator.events import bus
from app.tracing import trace


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(task_id: str, **fields) -> None:
    with new_session() as session:
        mission = session.get(Mission, task_id)
        if mission is None:
            return
        for key, value in fields.items():
            setattr(mission, key, value)
        mission.updated_at = _now()
        session.commit()


def _load_base_ctx(task_id: str) -> dict:
    with new_session() as session:
        mission = session.get(Mission, task_id)
        if mission is None:
            raise ValueError(f"任务不存在：{task_id}")
        return {
            "task_id": task_id,
            "goal": mission.goal,
            "constraints": dict(mission.constraints or {}),
        }


def _pending_gate(task_id: str) -> dict | None:
    with new_session() as session:
        gate = (
            session.query(ReviewGate)
            .filter(ReviewGate.mission_id == task_id, ReviewGate.action.is_(None))
            .order_by(ReviewGate.ts)
            .first()
        )
        if gate is None:
            return None
        return {"gate_id": gate.id, "type": gate.type, "param_id": gate.param_id,
                "message": f"待处理门禁：{gate.type}"}


STEP_META: list[tuple[str, str]] = [
    ("S1", "任务书解析"),
    ("S2", "检索先例与约束"),
    ("S3", "方案分解"),
    ("S4", "参数草案生成"),
    ("S5", "预算与计算"),
    ("S6", "一致性校验"),
    ("S7", "冲突消解建议"),
    ("S8", "叙述撰写"),
    ("S9", "文档渲染"),
]


def _step_defs():
    from app.steps import (
        s1_parse,
        s2_retrieve,
        s3_decompose,
        s4_params,
        s5_calc,
        s6_validate,
        s7_advise,
        s8_narrative,
        s9_render,
    )

    fns = {
        "S1": s1_parse.run,
        "S2": s2_retrieve.run,
        "S3": s3_decompose.run,
        "S4": s4_params.run,
        "S5": s5_calc.run,
        "S6": s6_validate.run,
        "S7": s7_advise.run,
        "S8": s8_narrative.run,
        "S9": s9_render.run,
    }
    return [(code, name, fns[code]) for code, name in STEP_META]


async def run_mission(task_id: str, start_from: str = "S1") -> None:
    defs = _step_defs()
    codes = [code for code, _, _ in defs]
    start_idx = codes.index(start_from)
    ctx = _load_base_ctx(task_id)

    _set_status(task_id, status="running", last_error=None)

    for code, name, fn in defs[start_idx:]:
        _set_status(task_id, current_step=code)
        bus.publish(task_id, "step", {"step": code, "name": name, "status": "running"})
        t0 = time.perf_counter()
        try:
            result = fn(ctx)
        except Exception as exc:  # noqa: BLE001 —— 步骤级失败统一记录
            duration = int((time.perf_counter() - t0) * 1000)
            trace(task_id, {"step": code, "type": "step", "status": "failed",
                            "error": str(exc), "duration_ms": duration})
            _set_status(task_id, status="failed",
                        last_error={"code": "INTERNAL", "message": str(exc)})
            bus.publish(task_id, "step", {"step": code, "name": name, "status": "failed",
                                          "message": str(exc)})
            bus.publish(task_id, "error", {"code": "INTERNAL", "message": str(exc)})
            return

        duration = int((time.perf_counter() - t0) * 1000)
        trace(task_id, {
            "step": code,
            "type": result.get("type", "step"),
            "status": "done",
            "output_ref": result.get("output_ref"),
            "validation_summary": result.get("validation_summary"),
            "blocked": result.get("blocked"),
            "duration_ms": duration,
        })
        bus.publish(task_id, "step", {"step": code, "name": name, "status": "done",
                                      "duration_ms": duration})

        if code == "S6":
            for finding in ctx.get("findings", []):
                bus.publish(task_id, "validation", finding)
            if ctx.get("blocked"):
                gate = _pending_gate(task_id)
                _set_status(task_id, status="awaiting_gate")
                if gate:
                    bus.publish(task_id, "gate", gate)
                    trace(task_id, {"step": "S10", "type": "gate", "status": "pending",
                                    "gate_id": gate["gate_id"], "param_id": gate["param_id"]})
                return

        # 成本上限守卫（docs/12 §4）
        with new_session() as session:
            mission = session.get(Mission, task_id)
            current_cost = float(mission.cost_estimate_cny or 0.0) if mission else 0.0
        if current_cost > settings.cost_limit_cny:
            message = f"任务成本 ¥{current_cost:.2f} 超过上限 ¥{settings.cost_limit_cny:.2f}，已中断"
            trace(task_id, {"step": code, "type": "step", "status": "failed", "error": "COST_LIMIT"})
            _set_status(task_id, status="failed", last_error={"code": "COST_LIMIT", "message": message})
            bus.publish(task_id, "error", {"code": "COST_LIMIT", "message": message})
            return

    _set_status(task_id, status="succeeded", current_step=None)
    bus.publish(task_id, "done", {"status": "succeeded"})
    trace(task_id, {"step": "S10", "type": "done", "status": "succeeded"})


def continue_mission(task_id: str) -> None:
    """门禁处理完成后从 S7 恢复（由评审接口调用）。"""
    _set_status(task_id, status="running")
    return run_mission(task_id, start_from="S7")
