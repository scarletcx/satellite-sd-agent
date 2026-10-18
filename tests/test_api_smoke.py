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


# ------------------------------------------------------------ 门禁驱动辅助


def _wait_status(client, task_id: str, statuses: tuple[str, ...], limit: int = 200) -> dict:
    detail: dict = {}
    for _ in range(limit):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in statuses:
            return detail
        time.sleep(0.05)
    raise AssertionError(f"等待状态 {statuses} 超时：{detail.get('status')}")


def _resolve_gate(client, task_id: str, *, include_needs_review: bool = True,
                  reviewer: str = "tester") -> dict:
    """处理当前门禁的待确认项：S4 草案输入、未确认假设，可选超限参数。"""
    wanted = ("draft", "needs_review") if include_needs_review else ("draft",)
    for _ in range(30):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] != "awaiting_gate":
            return detail
        acted = False
        items = client.get(f"/api/v1/missions/{task_id}/parameters", headers=HEADERS,
                           params={"page_size": 100}).json()["items"]
        for item in items:
            if item["status"] in wanted:
                response = client.post(
                    f"/api/v1/missions/{task_id}/parameters/{item['id']}/review",
                    headers=HEADERS,
                    json={"action": "accept", "reviewer": reviewer, "comment": "测试确认"},
                )
                assert response.status_code == 200, response.text
                acted = True
        assumptions = client.get(f"/api/v1/missions/{task_id}/assumptions", headers=HEADERS,
                                 params={"status": "open"}).json()["items"]
        for item in assumptions:
            response = client.post(
                f"/api/v1/missions/{task_id}/assumptions/{item['id']}/review",
                headers=HEADERS, json={"action": "accept", "reviewer": reviewer})
            assert response.status_code == 200, response.text
            acted = True
        if not acted:
            return detail
        time.sleep(0.05)
    raise AssertionError("门禁待确认项未能在限定轮次内处理完")


def _drive_to_terminal(client, task_id: str, limit: int = 200) -> dict:
    """反复处理门禁，直到任务 succeeded / failed。"""
    for _ in range(limit):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("succeeded", "failed"):
            return detail
        if detail["status"] == "awaiting_gate":
            _resolve_gate(client, task_id)
        time.sleep(0.05)
    raise AssertionError("任务未在限定轮次内结束")


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

    detail = _wait_status(client, task_id, ("awaiting_gate", "failed", "succeeded"))
    assert detail["status"] == "awaiting_gate"
    assert detail["pending_gates"], "S4 之后应产生输入确认门禁"
    assert detail["pending_gates"][0]["type"] == "confirm_inputs"
    assert detail["pending_confirmations"]["draft_inputs"] == 6, detail
    assert detail["pending_confirmations"]["open_assumptions"] >= 1

    detail = _drive_to_terminal(client, task_id)
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

    candidates = client.get(f"/api/v1/missions/{task_id}/candidates", headers=HEADERS)
    assert candidates.status_code == 200
    assert candidates.json()["total"] >= 4, "应生成选型候选（A15）"
    assumptions = client.get(f"/api/v1/missions/{task_id}/assumptions", headers=HEADERS)
    assert assumptions.status_code == 200
    assert assumptions.json()["total"] >= 1

    # A9 重新校验 → 文档版本递增（v1 → v2）
    revalidate = client.post(f"/api/v1/missions/{task_id}/revalidate", headers=HEADERS,
                             json={"scope": "all"})
    assert revalidate.status_code == 200, revalidate.text
    detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
    assert detail["document"]["versions"] == [1, 2], detail["document"]
    second = client.get(f"/api/v1/missions/{task_id}/document", headers=HEADERS,
                        params={"version": 2})
    assert second.status_code == 200 and second.content[:2] == b"PK"


def test_create_mission_rejects_unknown_provider(client):
    response = client.post("/api/v1/missions", headers=HEADERS,
                           json={"goal": "测试", "provider_id": "not-exist"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SCHEMA_INVALID"


def test_gate_review_resumes_mission(client):
    """门禁路径：输入确认 → 质量超限 → awaiting_gate → A8 放行 → 自动恢复到 succeeded。"""
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

    # 第一道门禁：输入确认（只确认输入，不放行后面的超限参数）
    detail = _wait_status(client, task_id, ("awaiting_gate", "failed", "succeeded"))
    assert detail["status"] == "awaiting_gate"
    assert detail["pending_gates"][0]["type"] == "confirm_inputs"
    _resolve_gate(client, task_id, include_needs_review=False)

    # 第二道门禁：质量超限（V4 block）
    detail = {}
    for _ in range(200):
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("succeeded", "failed"):
            raise AssertionError(detail)
        if (detail["status"] == "awaiting_gate"
                and any(gate["type"] == "discrepancy_resolve" for gate in detail["pending_gates"])):
            break
        time.sleep(0.05)
    assert detail["status"] == "awaiting_gate", detail
    assert detail["pending_confirmations"]["needs_review"] >= 1
    blocked_doc = client.get(f"/api/v1/missions/{task_id}/document", headers=HEADERS)
    assert blocked_doc.status_code == 409, "未放行前禁止导出"

    review = client.post(
        f"/api/v1/missions/{task_id}/parameters/mass.total_with_margin/review",
        headers=HEADERS,
        json={"action": "accept", "reviewer": "tester", "comment": "接受超限"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["revalidation"]["queued"] is True
    assert review.json()["gate"]["gate_id"], "全部确认完成后应关闭门禁"

    detail = _drive_to_terminal(client, task_id)
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
