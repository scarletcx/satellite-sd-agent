"""任务接口（docs/07 §A1~A5、A9、A11、A12；A10 docx 下载待渲染接入后实现）。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import api_error, require_token
from app.db import new_session
from app.models import DesignParameter, Mission, ReviewGate, ValidationResult
from app.orchestrator import engine
from app.orchestrator.events import bus
from app.orchestrator.ids import next_mission_id
from app.tracing import read_trace, task_dir

router = APIRouter(tags=["Missions"])


# ---------------------------------------------------------------- 请求模型


class MissionConstraints(BaseModel):
    orbit_type: Literal["SSO", "LEO", "GEO", "custom"] | None = None
    altitude_km: float | None = Field(default=None, ge=200, le=36000)
    inclination_deg: float | None = Field(default=None, ge=0, le=180)
    lifetime_years: float | None = Field(default=None, ge=0.5, le=20)
    payload: str | None = Field(default=None, max_length=500)
    data_requirements: str | None = Field(default=None, max_length=500)
    ttc_conditions: str | None = Field(default=None, max_length=500)
    mass_limit_kg: float | None = Field(default=None, gt=0)
    power_limit_w: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)


class MissionCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    constraints: MissionConstraints | None = None
    provider_id: str | None = Field(default=None, max_length=32,
                                    description="任务级模型选择（供应商 id）；空 = 按设置页降级链")
    language: Literal["zh"] = "zh"


class RevalidateBody(BaseModel):
    scope: str = "all"


# ---------------------------------------------------------------- 视图组装


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _steps_view(mission: Mission) -> list[dict]:
    codes = [code for code, _ in engine.STEP_META]
    if mission.status == "succeeded":
        reached = len(codes)
    elif mission.current_step and mission.current_step in codes:
        reached = codes.index(mission.current_step) + 1
    else:
        reached = 0
    steps = []
    for index, (code, name) in enumerate(engine.STEP_META):
        if index < reached:
            status = "done"
        elif index == reached and mission.status in ("running", "awaiting_gate"):
            status = "running" if mission.status == "running" else "pending"
        else:
            status = "pending"
        steps.append({"code": code, "name": name, "status": status, "duration_ms": None})
    return steps


def _provider_model(provider_id: str | None) -> str | None:
    if not provider_id:
        return None
    try:
        from app.providers.specs import find_spec

        spec = find_spec(provider_id)
        return spec.model if spec else None
    except Exception:  # noqa: BLE001
        return None


def _detail_payload(mission_id: str) -> dict:
    with new_session() as session:
        mission = session.get(Mission, mission_id)
        if mission is None:
            api_error(404, "MISSION_NOT_FOUND", "任务不存在", {"task_id": mission_id})
        gates = (
            session.query(ReviewGate)
            .filter(ReviewGate.mission_id == mission_id, ReviewGate.action.is_(None))
            .order_by(ReviewGate.ts)
            .all()
        )
        pending = [{"gate_id": g.id, "type": g.type, "param_id": g.param_id,
                    "message": f"待处理门禁：{g.type}"} for g in gates]
        documents = sorted(
            task_dir(mission_id).glob("document-v*.docx"),
            key=lambda p: int(p.stem.rsplit("-v", 1)[1]),
        )
        document = {
            "ready": bool(documents),
            "version": int(documents[-1].stem.rsplit("-v", 1)[1]) if documents else None,
            "url": f"/api/v1/missions/{mission_id}/document" if documents else None,
        }
        return {
            "task_id": mission.id,
            "goal": mission.goal,
            "status": mission.status,
            "current_step": mission.current_step,
            "provider_id": mission.provider_id,
            "provider_model": _provider_model(mission.provider_id),
            "steps": _steps_view(mission),
            "cost_estimate_cny": mission.cost_estimate_cny,
            "document": document,
            "pending_gates": pending,
            "last_error": mission.last_error,
            "corpus_version": mission.corpus_version,
            "created_at": _iso(mission.created_at),
            "updated_at": _iso(mission.updated_at),
        }


# ---------------------------------------------------------------- A1 创建


@router.post("/missions", status_code=202)
async def create_mission(payload: MissionCreate, _: None = Depends(require_token)) -> dict:
    if payload.provider_id:
        from app.providers.specs import find_spec

        spec = find_spec(payload.provider_id)
        if spec is None or not spec.enabled:
            api_error(400, "SCHEMA_INVALID",
                      f"供应商不存在或未启用：{payload.provider_id}", {"field": "provider_id"})
        if not (spec.api_key or spec.keyless):
            api_error(400, "SCHEMA_INVALID",
                      f"供应商未配置密钥：{payload.provider_id}", {"field": "provider_id"})

    with new_session() as session:
        task_id = next_mission_id(session)
        mission = Mission(
            id=task_id,
            goal=payload.goal,
            constraints=(payload.constraints.model_dump(exclude_none=True) if payload.constraints else {}),
            provider_id=payload.provider_id or None,
            status="queued",
        )
        session.add(mission)
        session.commit()
        created_at = mission.created_at

    asyncio.create_task(engine.run_mission(task_id))
    return {"task_id": task_id, "status": "queued", "created_at": _iso(created_at)}


# ---------------------------------------------------------------- A2 列表


@router.get("/missions")
def list_missions(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_token),
) -> dict:
    with new_session() as session:
        query = session.query(Mission)
        if status:
            query = query.filter(Mission.status == status)
        total = query.count()
        rows = (query.order_by(Mission.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size).all())
        items = [{
            "task_id": m.id, "goal": m.goal, "status": m.status,
            "current_step": m.current_step, "cost_estimate_cny": m.cost_estimate_cny,
            "created_at": _iso(m.created_at), "updated_at": _iso(m.updated_at),
        } for m in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------- A3 详情


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str, _: None = Depends(require_token)) -> dict:
    return _detail_payload(mission_id)


# ---------------------------------------------------------------- A4 SSE


@router.get("/missions/{mission_id}/events")
async def mission_events(mission_id: str, request: Request, _: None = Depends(require_token)):
    _detail_payload(mission_id)  # 校验存在性

    queue = bus.subscribe(mission_id)

    def sse(eid: int | None, event: str, data: dict) -> str:
        head = f"id: {eid}\n" if eid is not None else ""
        return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def generator():
        try:
            yield sse(0, "snapshot", _detail_payload(mission_id))
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield sse(None, "ping", {})
                    continue
                yield sse(item["id"], item["event"], item["data"])
                if item["event"] in ("done", "error"):
                    break
        finally:
            bus.unsubscribe(mission_id, queue)

    return StreamingResponse(generator(), media_type="text/event-stream")


# ---------------------------------------------------------------- A5 取消


@router.post("/missions/{mission_id}/cancel")
def cancel_mission(mission_id: str, _: None = Depends(require_token)) -> dict:
    with new_session() as session:
        mission = session.get(Mission, mission_id)
        if mission is None:
            api_error(404, "MISSION_NOT_FOUND", "任务不存在", {"task_id": mission_id})
        if mission.status in ("queued", "running", "awaiting_gate"):
            mission.status = "canceled"
            session.commit()
        elif mission.status != "canceled":
            api_error(409, "STATE_CONFLICT", "当前任务状态不允许取消", {"status": mission.status})
        return {"task_id": mission.id, "status": mission.status}


# ---------------------------------------------------------------- A9 重新校验


@router.post("/missions/{mission_id}/revalidate")
async def revalidate(mission_id: str, body: RevalidateBody | None = None,
                     _: None = Depends(require_token)) -> dict:
    with new_session() as session:
        mission = session.get(Mission, mission_id)
        if mission is None:
            api_error(404, "MISSION_NOT_FOUND", "任务不存在", {"task_id": mission_id})
        if mission.status == "canceled":
            api_error(409, "STATE_CONFLICT", "任务已取消", {"status": mission.status})

    # 骨架阶段：桩模式下毫秒级，直接同步执行（真实模型接入后改为后台任务）
    await engine.run_mission(mission_id, start_from="S6")

    with new_session() as session:
        latest = (session.query(ValidationResult)
                  .filter(ValidationResult.mission_id == mission_id)
                  .order_by(ValidationResult.created_at.desc())
                  .limit(20).all())
        summary = {"pass": 0, "warn": 0, "block": 0}
        for row in latest:
            summary[row.status] = summary.get(row.status, 0) + 1
        blocking = [{"rule": r.rule_id, "param_id": r.param_id, "message": r.message}
                    for r in latest if r.status == "block"]
    return {"queued": True, "scope": body.scope if body else "all",
            "summary": summary, "blocking": blocking}


# ---------------------------------------------------------------- A10 文档


def _resolve_document(mission_id: str, version: int | None):
    """文档存在性 / 门禁检查（A10 与预览共用）。"""
    _detail_payload(mission_id)
    directory = task_dir(mission_id)

    with new_session() as session:
        blocking = [
            {"rule": "PARAM_STATE", "param_id": p.id,
             "message": f"参数 {p.id} 状态为 {p.status}，未通过评审"}
            for p in session.query(DesignParameter)
            .filter(DesignParameter.mission_id == mission_id,
                    DesignParameter.status.in_(("needs_review", "rejected")))
            .all()
        ]
    if blocking:
        api_error(409, "DOC_NOT_READY", "存在未通过的参数，禁止导出", {"blocking": blocking})

    if version is not None:
        target = directory / f"document-v{version}.docx"
        if not target.exists():
            api_error(404, "DOC_NOT_FOUND", "指定版本文档不存在", {"version": version})
        return target

    documents = sorted(directory.glob("document-v*.docx"),
                       key=lambda p: int(p.stem.rsplit("-v", 1)[1]))
    if not documents:
        api_error(409, "DOC_NOT_READY", "文档尚未生成", {"reason": "not_generated"})
    return documents[-1]


@router.get("/missions/{mission_id}/document")
def download_document(mission_id: str, version: int | None = Query(default=None, ge=1),
                      _: None = Depends(require_token)):
    target = _resolve_document(mission_id, version)
    return FileResponse(
        str(target),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{mission_id}-design-{target.stem}.docx",
    )


@router.get("/missions/{mission_id}/document/preview")
def preview_document(mission_id: str, version: int | None = Query(default=None, ge=1),
                     _: None = Depends(require_token)) -> dict:
    """Word 在线预览：docx → HTML（mammoth），供前端直接渲染。"""
    target = _resolve_document(mission_id, version)

    import mammoth

    with target.open("rb") as handle:
        result = mammoth.convert_to_html(handle)
    return {
        "task_id": mission_id,
        "version": int(target.stem.rsplit("-v", 1)[1]),
        "html": result.value,
        "warnings": [message.message for message in result.messages][:10],
    }


# ---------------------------------------------------------------- A11 trace


@router.get("/missions/{mission_id}/trace")
def export_trace(mission_id: str, format: str = Query(default="jsonl", pattern="^(jsonl|json)$"),
                 _: None = Depends(require_token)):
    _detail_payload(mission_id)
    events = read_trace(mission_id)
    if format == "json":
        return {"task_id": mission_id, "event_count": len(events), "events": events}
    text = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
    return PlainTextResponse(text + ("\n" if text else ""), media_type="application/x-ndjson")


# ------------------------------------------------------------ A12 校验报告


@router.get("/missions/{mission_id}/check-report")
def check_report(mission_id: str, _: None = Depends(require_token)) -> dict:
    _detail_payload(mission_id)
    path = task_dir(mission_id) / "check-report.json"
    if not path.exists():
        api_error(404, "DOC_NOT_FOUND", "校验报告尚未生成", {"task_id": mission_id})
    return json.loads(path.read_text(encoding="utf-8"))
