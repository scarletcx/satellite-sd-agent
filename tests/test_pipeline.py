"""端到端流水线测试（桩模式，docs/11 §3 E2E-01 / ADV-04 门禁路径）。"""
import asyncio
import json

import pytest
from docx import Document

from app.db import init_db, new_session
from app.models import DesignParameter, Mission, ReviewGate, ValidationResult
from app.orchestrator import engine
from app.orchestrator.ids import next_mission_id
from app.tracing import read_trace, task_dir
from tests.seed_kb import seed as seed_kb


def _create_mission(constraints: dict) -> str:
    with new_session() as session:
        task_id = next_mission_id(session)
        session.add(Mission(
            id=task_id,
            goal="设计一颗 500km SSO 光学遥感小卫星",
            constraints=constraints,
            status="queued",
        ))
        session.commit()
    return task_id


def test_pipeline_end_to_end():
    init_db()
    seed_kb()
    task_id = _create_mission({"orbit_type": "SSO", "altitude_km": 500,
                               "lifetime_years": 3, "mass_limit_kg": 80})
    asyncio.run(engine.run_mission(task_id))

    with new_session() as session:
        mission = session.get(Mission, task_id)
        assert mission.status == "succeeded", mission.last_error

        params = {p.id: p for p in session.query(DesignParameter)
                  .filter_by(mission_id=task_id).all()}
        assert len(params) >= 22
        assert params["mass.total"].value > 0
        assert params["mass.total_with_margin"].value > params["mass.total"].value
        assert params["mass.total_with_margin"].status == "verified"
        assert params["power.battery_capacity_wh"].value > 0
        # C4/C5/C6 已接入：轨道、太阳翼、链路
        assert params["orbit.period_min"].value == pytest.approx(94.6, abs=1.5)
        assert params["orbit.orbits_per_day"].value > 15
        assert params["power.sa.area"].value > 0
        assert params["link.margin_db"].value > 3

        results = session.query(ValidationResult).filter_by(mission_id=task_id).all()
        assert results and all(r.status != "block" for r in results)

    directory = task_dir(task_id)
    report = json.loads((directory / "check-report.json").read_text(encoding="utf-8"))
    assert report["placeholders_left"] == 0
    assert report["status"] == "pass"
    assert report["numbers_checked"] > 0
    assert (directory / "document-v1.docx").exists()

    # 引用链路：检索 → citations.json → 文档附录
    citations = json.loads((directory / "citations.json").read_text(encoding="utf-8"))
    assert citations, "S2 应检索到引用"
    assert report["citations"] == len(citations)
    document = Document(str(directory / "document-v1.docx"))
    texts = [p.text for p in document.paragraphs]
    texts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    assert citations[0]["title"] in "\n".join(texts), "附录应包含引用来源"

    events = read_trace(task_id)
    assert len(events) >= 9


def test_pipeline_gate_on_mass_limit():
    init_db()
    seed_kb()
    task_id = _create_mission({"orbit_type": "SSO", "altitude_km": 500,
                               "mass_limit_kg": 70})
    asyncio.run(engine.run_mission(task_id))

    with new_session() as session:
        mission = session.get(Mission, task_id)
        assert mission.status == "awaiting_gate", mission.last_error
        gate = (session.query(ReviewGate)
                .filter(ReviewGate.mission_id == task_id, ReviewGate.action.is_(None))
                .first())
        assert gate is not None
        param = session.get(DesignParameter, ("mass.total_with_margin", task_id))
        assert param.status == "needs_review"
        # 人工放行（模拟 A8 accept）
        gate.action = "accept"
        gate.reviewer = "tester"
        param.status = "verified"
        session.commit()

    asyncio.run(engine.continue_mission(task_id))
    with new_session() as session:
        assert session.get(Mission, task_id).status == "succeeded"
