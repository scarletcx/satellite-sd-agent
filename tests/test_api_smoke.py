"""API 冒烟测试（docs/11 §1 L4 轻量版）。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_no_auth(client):
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_info_requires_auth(client):
    assert client.get("/api/v1/info").status_code == 401


def test_create_mission_and_complete(client):
    response = client.post(
        "/api/v1/missions",
        headers=HEADERS,
        json={
            "goal": "设计一颗 500km SSO 光学遥感小卫星",
            "constraints": {"orbit_type": "SSO", "altitude_km": 500, "mass_limit_kg": 80},
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]

    detail = {}
    for _ in range(120):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("succeeded", "failed", "awaiting_gate"):
            break
        time.sleep(0.05)
    assert detail["status"] == "succeeded", detail

    params = client.get(f"/api/v1/missions/{task_id}/parameters", headers=HEADERS).json()
    assert params["total"] >= 14

    report = client.get(f"/api/v1/missions/{task_id}/check-report", headers=HEADERS)
    assert report.status_code == 200
    assert report.json()["placeholders_left"] == 0

    trace = client.get(f"/api/v1/missions/{task_id}/trace", headers=HEADERS,
                       params={"format": "json"}).json()
    assert trace["event_count"] >= 9

    document = client.get(f"/api/v1/missions/{task_id}/document", headers=HEADERS)
    assert document.status_code == 200
    assert document.content[:2] == b"PK"  # docx = zip 包
    assert "wordprocessingml" in document.headers["content-type"]

    preview = client.get(f"/api/v1/missions/{task_id}/document/preview", headers=HEADERS)
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["version"] == 1
    assert "卫星整星详细设计方案" in payload["html"]
    assert "<table>" in payload["html"]  # 预算表已转换为 HTML 表格


def test_create_mission_rejects_unknown_provider(client):
    response = client.post("/api/v1/missions", headers=HEADERS,
                           json={"goal": "测试", "provider_id": "not-exist"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SCHEMA_INVALID"


def test_gate_review_resumes_mission(client):
    """门禁路径：mass_limit 超限 → awaiting_gate → A8 放行 → 自动恢复到 succeeded。"""
    response = client.post(
        "/api/v1/missions",
        headers=HEADERS,
        json={
            "goal": "设计一颗 500km SSO 光学遥感小卫星",
            "constraints": {"orbit_type": "SSO", "altitude_km": 500, "mass_limit_kg": 70},
        },
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]

    detail = {}
    for _ in range(120):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("awaiting_gate", "failed", "succeeded"):
            break
        time.sleep(0.05)
    assert detail["status"] == "awaiting_gate", detail
    assert detail["pending_gates"], "应存在待处理门禁"
    blocked_doc = client.get(f"/api/v1/missions/{task_id}/document", headers=HEADERS)
    assert blocked_doc.status_code == 409, "未放行前禁止导出"

    review = client.post(
        f"/api/v1/missions/{task_id}/parameters/mass.total_with_margin/review",
        headers=HEADERS,
        json={"action": "accept", "reviewer": "tester", "comment": "接受超限"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["revalidation"]["queued"] is True

    detail = {}
    for _ in range(120):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert detail["status"] == "succeeded", detail
    document = client.get(f"/api/v1/missions/{task_id}/document", headers=HEADERS)
    assert document.status_code == 200 and document.content[:2] == b"PK"


def test_kb_ingest_search_delete(client):
    """知识库接口闭环：摄取 → 检索命中 → 删除。"""
    response = client.post(
        "/api/v1/kb/ingest",
        headers=HEADERS,
        files={"file": ("sample.txt", "测试语料：太阳翼面积估算与电池容量计算方法。".encode(), "text/plain")},
        data={"module": "power", "doc_type": "report", "license": "synthetic",
              "is_synthetic": "true", "title": "接口测试样例"},
    )
    assert response.status_code == 201, response.text
    doc_id = response.json()["doc_id"]

    search = client.post("/api/v1/kb/search", headers=HEADERS,
                         json={"query": "太阳翼面积估算", "top_k": 5})
    assert search.status_code == 200
    assert any(item["doc_id"] == doc_id for item in search.json()["results"])

    stats = client.get("/api/v1/kb/stats", headers=HEADERS).json()
    assert stats["documents"] >= 1

    deleted = client.delete(f"/api/v1/kb/documents/{doc_id}", headers=HEADERS,
                            params={"confirm": "true"})
    assert deleted.status_code == 200
    assert deleted.json()["doc_id"] == doc_id
