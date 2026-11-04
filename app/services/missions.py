"""任务服务：创建（含后台调度）、列表、快照、重命名；供 API 与聊天工具复用。"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone

from app.db import new_session
from app.models import Mission, ReviewGate
from app.orchestrator.ids import next_mission_id


class MissionError(LookupError):
    def __init__(self, message: str, *, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


def default_title(goal: str) -> str:
    first = (goal or "").strip().splitlines()[0] if (goal or "").strip() else "未命名任务"
    return first[:40]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _launch(task_id: str) -> None:
    """任务流水线在后台线程执行（本地单用户，无需任务队列）。"""
    from app.orchestrator import engine

    def runner() -> None:
        asyncio.run(engine.run_mission(task_id))

    threading.Thread(target=runner, daemon=True, name=f"mission-{task_id}").start()


def create_mission(*, goal: str, constraints: dict | None = None,
                   provider_id: str | None = None, title: str | None = None) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise MissionError("任务目标不能为空")
    with new_session() as session:
        task_id = next_mission_id(session)
        row = Mission(
            id=task_id, goal=goal,
            title=(title or "").strip()[:120] or None,
            constraints=dict(constraints or {}),
            provider_id=provider_id or None,
            status="queued",
        )
        session.add(row)
        session.commit()
        created_at = row.created_at
    _launch(task_id)
    return {"task_id": task_id, "title": title or default_title(goal),
            "status": "queued", "created_at": _iso(created_at)}


def list_missions(status: str | None = None, limit: int = 50) -> list[dict]:
    with new_session() as session:
        query = session.query(Mission)
        if status:
            query = query.filter(Mission.status == status)
        rows = (query.order_by(Mission.created_at.desc(), Mission.id.desc())
                .limit(limit).all())
        return [
            {
                "task_id": row.id,
                "title": row.title or default_title(row.goal),
                "goal": row.goal,
                "status": row.status,
                "current_step": row.current_step,
                "cost_estimate_cny": row.cost_estimate_cny,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in rows
        ]


def mission_snapshot(task_id: str) -> dict:
    with new_session() as session:
        row = session.get(Mission, task_id)
        if row is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        gates = (session.query(ReviewGate)
                 .filter(ReviewGate.mission_id == task_id, ReviewGate.action.is_(None))
                 .all())
        return {
            "task_id": row.id,
            "title": row.title or default_title(row.goal),
            "goal": row.goal,
            "status": row.status,
            "current_step": row.current_step,
            "cost_estimate_cny": row.cost_estimate_cny,
            "pending_gates": [{"gate_id": gate.id, "type": gate.type,
                               "param_id": gate.param_id} for gate in gates],
            "last_error": row.last_error,
            "updated_at": _iso(row.updated_at),
        }


def mission_progress(task_id: str) -> dict:
    """任务实时进度：步骤、百分比、门禁、待确认项、最近事件。"""
    from sqlalchemy import func

    from app.models import Assumption, DesignParameter, ValidationResult
    from app.orchestrator.engine import STEP_META
    from app.orchestrator.events import bus

    with new_session() as session:
        mission = session.get(Mission, task_id)
        if mission is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        gates = (session.query(ReviewGate)
                 .filter(ReviewGate.mission_id == task_id,
                         ReviewGate.action.is_(None))
                 .order_by(ReviewGate.ts).all())
        status_counts = dict(
            session.query(DesignParameter.status, func.count())
            .filter(DesignParameter.mission_id == task_id)
            .group_by(DesignParameter.status).all())
        open_assumptions = (session.query(Assumption)
                            .filter(Assumption.mission_id == task_id,
                                    Assumption.status == "open").count())
        validations = (session.query(ValidationResult)
                       .filter(ValidationResult.mission_id == task_id)
                       .order_by(ValidationResult.created_at.desc()).limit(50).all())
        latest_ts = validations[0].created_at if validations else None
        if latest_ts is not None:
            validations = [row for row in validations
                           if (latest_ts - row.created_at).total_seconds() <= 2.0]
        validation_summary = {"pass": 0, "warn": 0, "block": 0}
        for row in validations:
            validation_summary[row.status] = validation_summary.get(row.status, 0) + 1
        blocking = [row.param_id for row in validations
                    if row.status == "block" and row.param_id]
        data = {
            "task_id": mission.id,
            "title": mission.title or default_title(mission.goal),
            "goal": mission.goal,
            "status": mission.status,
            "current_step": mission.current_step,
            "cost_estimate_cny": mission.cost_estimate_cny,
            "last_error": mission.last_error,
            "updated_at": _iso(mission.updated_at),
            "pending_gates": [{"gate_id": g.id, "type": g.type, "param_id": g.param_id}
                              for g in gates],
            "pending_confirmations": {
                "draft_inputs": status_counts.get("draft", 0),
                "needs_review": status_counts.get("needs_review", 0),
                "rejected": status_counts.get("rejected", 0),
                "open_assumptions": open_assumptions,
            },
            "validation": validation_summary,
            "blocking_params": sorted(set(blocking)),
        }

    codes = [code for code, _ in STEP_META]
    if data["status"] == "succeeded":
        reached = len(codes)
    elif data["current_step"] in codes:
        reached = codes.index(data["current_step"]) + 1
    else:
        reached = 0
    steps = []
    for index, (code, name) in enumerate(STEP_META):
        if index < reached:
            step_status = "done"
        elif index == reached and data["status"] in ("running", "awaiting_gate"):
            step_status = "running" if data["status"] == "running" else "pending"
        else:
            step_status = "pending"
        steps.append({"code": code, "name": name, "status": step_status})
    done = sum(1 for step in steps if step["status"] == "done")
    data["steps"] = steps
    data["done_steps"] = done
    data["total_steps"] = len(steps)
    data["percent"] = 100 if data["status"] == "succeeded" else round(done / max(len(steps), 1) * 100)
    data["recent_events"] = [
        {"id": item["id"], "event": item["event"], "data": item.get("data") or {}}
        for item in bus.history_since(task_id, 0)[-8:]
    ]
    return data


def mission_results(task_id: str) -> dict:
    """任务结果：关键参数、校验汇总、假设、选型、引用与文档状态。"""
    import json

    from app.models import (Assumption, CalculationRecord, DesignParameter,
                            SelectionCandidate, ValidationResult)
    from app.tracing import task_dir

    key_ids = ("mass.total_with_margin", "mass.dry", "power.p_avg_w", "power.sa.area",
               "link.margin_db", "orbit.period_min", "data.per_day_gb",
               "adcs.h_required_nms")
    with new_session() as session:
        mission = session.get(Mission, task_id)
        if mission is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        params = {row.id: row for row in session.query(DesignParameter)
                  .filter(DesignParameter.mission_id == task_id).all()}
        metrics = []
        for param_id in key_ids:
            row = params.get(param_id)
            if row is not None:
                metrics.append({"id": row.id, "name": row.name, "value": row.value,
                                "unit": row.unit, "status": row.status,
                                "source_ref": row.source_ref})
        validations = (session.query(ValidationResult)
                       .filter(ValidationResult.mission_id == task_id)
                       .order_by(ValidationResult.created_at.desc()).limit(50).all())
        latest_ts = validations[0].created_at if validations else None
        if latest_ts is not None:
            validations = [row for row in validations
                           if (latest_ts - row.created_at).total_seconds() <= 2.0]
        validation_summary = {"pass": 0, "warn": 0, "block": 0}
        blocking = []
        for row in validations:
            validation_summary[row.status] = validation_summary.get(row.status, 0) + 1
            if row.status == "block":
                blocking.append({"rule": row.rule_id, "param_id": row.param_id,
                                 "message": row.message})
        assumption_counts = {"open": 0, "confirmed": 0, "rejected": 0}
        for row in session.query(Assumption).filter(Assumption.mission_id == task_id).all():
            assumption_counts[row.status] = assumption_counts.get(row.status, 0) + 1
        candidates = (session.query(SelectionCandidate)
                      .filter(SelectionCandidate.mission_id == task_id).count())
        calculations = (session.query(CalculationRecord)
                        .filter(CalculationRecord.mission_id == task_id).count())
        data = {
            "task_id": mission.id,
            "title": mission.title or default_title(mission.goal),
            "goal": mission.goal,
            "status": mission.status,
            "current_step": mission.current_step,
            "last_error": mission.last_error,
            "metrics": metrics,
            "parameter_count": len(params),
            "calculation_count": calculations,
            "validation": validation_summary,
            "blocking": blocking[:8],
            "assumptions": assumption_counts,
            "candidates": candidates,
            "document": {"ready": False, "version": None, "versions": []},
            "check_report": None,
            "citations": 0,
        }

    directory = task_dir(task_id)
    documents = sorted(directory.glob("document-v*.docx"),
                       key=lambda p: int(p.stem.rsplit("-v", 1)[1]))
    versions = [int(p.stem.rsplit("-v", 1)[1]) for p in documents]
    data["document"] = {"ready": bool(documents),
                        "version": versions[-1] if versions else None,
                        "versions": versions}
    report_path = directory / "check-report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            data["check_report"] = {
                "status": report.get("status"),
                "placeholders_left": report.get("placeholders_left"),
                "numbers_checked": report.get("numbers_checked"),
                "numbers_traceable": report.get("numbers_traceable"),
                "citation_issues": report.get("citation_issues"),
            }
        except Exception:  # noqa: BLE001
            data["check_report"] = None
    citations_path = directory / "citations.json"
    if citations_path.exists():
        try:
            data["citations"] = len(json.loads(citations_path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            data["citations"] = 0
    return data


def rename_mission(task_id: str, title: str) -> dict:
    title = (title or "").strip()[:120]
    if not title:
        raise MissionError("任务名称不能为空")
    with new_session() as session:
        row = session.get(Mission, task_id)
        if row is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        row.title = title
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"task_id": row.id, "title": row.title}


def delete_mission(task_id: str, *, reviewer: str = "engineer") -> dict:
    """删除任务及其全部关联数据（参数/计算/校验/假设/门禁/选型/审计）与制品目录。"""
    import shutil

    from app.models import (
        Assumption,
        AuditLog,
        CalculationRecord,
        DesignParameter,
        ReviewGate,
        SelectionCandidate,
        ValidationResult,
    )
    from app.orchestrator.events import bus
    from app.tracing import task_dir

    with new_session() as session:
        row = session.get(Mission, task_id)
        if row is None:
            raise MissionError(f"任务不存在：{task_id}", not_found=True)
        if row.status in ("queued", "running"):
            raise MissionError("任务正在执行，请先取消再删除")

        removed = {}
        for model, name in ((DesignParameter, "parameters"),
                            (CalculationRecord, "calculations"),
                            (ValidationResult, "validations"),
                            (Assumption, "assumptions"),
                            (ReviewGate, "gates"),
                            (SelectionCandidate, "candidates")):
            removed[name] = (session.query(model)
                             .filter(model.mission_id == task_id)
                             .delete(synchronize_session=False))
        session.add(AuditLog(
            entity="mission", entity_id=task_id, field="delete",
            before={"status": row.status, "title": row.title or row.goal},
            who=reviewer, why="A17 删除任务",
        ))
        session.delete(row)
        session.commit()

    shutil.rmtree(task_dir(task_id), ignore_errors=True)
    bus.forget(task_id)
    return {"task_id": task_id, "deleted": True, "removed": removed}
