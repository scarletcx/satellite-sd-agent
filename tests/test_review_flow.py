"""评审增强测试：一键确认、草案参数编辑、驳回终止、模型窗口参考、命令调整。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create(client, mass_limit=80) -> str:
    return client.post("/api/v1/missions", headers=HEADERS, json={
        "goal": "设计一颗 500km SSO 光学遥感小卫星",
        "constraints": {"orbit_type": "SSO", "altitude_km": 500, "mass_limit_kg": mass_limit},
    }).json()["task_id"]


def _wait(client, task_id: str, statuses=("awaiting_gate", "succeeded", "failed"),
          timeout_s: float = 8.0) -> dict:
    deadline = time.time() + timeout_s
    detail: dict = {}
    while time.time() < deadline:
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in statuses:
            return detail
        time.sleep(0.05)
    return detail


def test_accept_all_reviews_and_resume(client):
    task_id = _create(client)
    detail = _wait(client, task_id)
    assert detail["status"] == "awaiting_gate"

    result = client.post(f"/api/v1/missions/{task_id}/reviews/accept-all",
                         headers=HEADERS, json={"reviewer": "tester"})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["accepted_parameters"] >= 6
    assert payload["accepted_assumptions"] >= 1
    assert payload["remaining_confirmations"] == 0
    assert payload["revalidation"]["queued"] is True

    detail = _wait(client, task_id, ("succeeded", "failed"))
    assert detail["status"] == "succeeded", detail


def test_edit_group_draft_payload(client):
    task_id = _create(client)
    _wait(client, task_id)
    detail = client.get(f"/api/v1/missions/{task_id}/parameters/input.mass",
                        headers=HEADERS).json()
    payload = dict(detail["payload"])
    payload["propellant_kg"] = 5.0  # 原值 3.0

    accepted = client.post(f"/api/v1/missions/{task_id}/parameters/input.mass/review",
                           headers=HEADERS, json={
                               "action": "accept", "reviewer": "tester",
                               "comment": "推进剂按 5kg 复核",
                               "edited_payload": payload,
                           })
    assert accepted.status_code == 200, accepted.text

    # 其余待确认项一键处理，让任务继续
    result = client.post(f"/api/v1/missions/{task_id}/reviews/accept-all",
                         headers=HEADERS, json={"reviewer": "tester"})
    assert result.status_code == 200
    detail = _wait(client, task_id, ("succeeded", "failed"))
    assert detail["status"] in ("succeeded", "awaiting_gate")

    param = client.get(f"/api/v1/missions/{task_id}/parameters/mass.propellant",
                       headers=HEADERS).json()
    assert param["value"] == pytest.approx(5.0)


def test_reject_draft_fails_mission(client):
    task_id = _create(client)
    _wait(client, task_id)
    rejected = client.post(f"/api/v1/missions/{task_id}/parameters/input.power/review",
                           headers=HEADERS, json={
                               "action": "reject", "reviewer": "tester",
                               "comment": "功耗假设不合理",
                           })
    assert rejected.status_code == 200, rejected.text
    assert rejected.json().get("mission_failed") is True

    detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
    assert detail["status"] == "failed"
    assert detail["last_error"]["code"] == "REVIEW_REJECTED"


def test_chat_can_accept_all_latest_mission(client):
    task_id = _create(client)
    _wait(client, task_id)
    session_id = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]
    reply = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                        json={"content": "帮我自动完成审核"})
    assert reply.status_code == 200, reply.text
    assistant = reply.json()["assistant"]
    assert "已一键确认" in assistant["content"] or "一键" in assistant["content"]

    detail = _wait(client, task_id, ("succeeded", "failed"))
    assert detail["status"] == "succeeded", detail


def test_context_settings_default_and_command_removed(client):
    settings = client.get("/api/v1/settings/chat", headers=HEADERS).json()
    assert settings["default_window"] == 256_000

    session_id = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]
    reply = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                        json={"content": "/context"})
    assert reply.status_code == 200
    assert "未知命令" in reply.json()["assistant"]["content"]


def test_delete_mission_removes_related_data(client):
    task_id = _create(client)
    _wait(client, task_id)
    canceled = client.post(f"/api/v1/missions/{task_id}/cancel", headers=HEADERS)
    assert canceled.status_code == 200, canceled.text

    refused = client.delete(f"/api/v1/missions/{task_id}", headers=HEADERS)
    assert refused.status_code == 400, refused.text

    deleted = client.delete(f"/api/v1/missions/{task_id}?confirm=true", headers=HEADERS)
    assert deleted.status_code == 200, deleted.text
    payload = deleted.json()
    assert payload["deleted"] is True
    assert payload["removed"]["parameters"] >= 1
    assert payload["removed"]["gates"] >= 1

    assert client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).status_code == 404
    assert all(item["task_id"] != task_id
               for item in client.get("/api/v1/missions", headers=HEADERS).json()["items"])
    assert client.delete(f"/api/v1/missions/{task_id}?confirm=true",
                         headers=HEADERS).status_code == 404


def test_accept_all_rounds_through_new_gate(client):
    """一键确认应在一次调用内处理输入门禁，以及随后出现的新校验门禁（如质量超限）。"""
    task_id = _create(client, mass_limit=70)
    detail = _wait(client, task_id)
    assert detail["status"] == "awaiting_gate"

    result = client.post(f"/api/v1/missions/{task_id}/reviews/accept-all",
                         headers=HEADERS, json={"reviewer": "tester"})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["rounds"] >= 2
    assert payload["remaining_confirmations"] == 0

    detail = _wait(client, task_id, ("succeeded", "failed"), timeout_s=12)
    assert detail["status"] == "succeeded", detail
