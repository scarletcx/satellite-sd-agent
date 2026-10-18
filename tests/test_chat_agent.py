"""个人 agent 增强功能测试：上下文压缩、长期记忆、模型切换、任务命名、流式输出。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _new_session(client) -> str:
    return client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]


def _wait_mission(client, task_id: str, timeout_s: float = 8.0) -> dict:
    deadline = time.time() + timeout_s
    detail: dict = {}
    while time.time() < deadline:
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in ("awaiting_gate", "succeeded", "failed"):
            return detail
        time.sleep(0.05)
    return detail


def test_context_settings_and_manual_compact(client):
    session_id = _new_session(client)
    updated = client.put("/api/v1/settings/chat", headers=HEADERS,
                         json={"auto_compact": False, "threshold_pct": 70, "keep_recent": 6})
    assert updated.status_code == 200
    assert updated.json()["auto_compact"] is False
    assert updated.json()["threshold_pct"] == 70

    for index in range(6):
        response = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                               json={"content": f"第 {index} 轮：请记住一个短句 {index}"})
        assert response.status_code == 200

    compacted = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                            json={"content": "/compact"})
    assert compacted.status_code == 200
    assert "压缩" in compacted.json()["assistant"]["content"]

    snapshot = client.get(f"/api/v1/chat/sessions/{session_id}/context", headers=HEADERS).json()
    assert snapshot["compacted_until"] > 0
    assert snapshot["pending_messages"] <= snapshot["keep_recent"] + 2

    # 全量消息仍在数据库（压缩只影响发送给模型的内容）
    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS).json()
    assert messages["total"] >= 14


def test_long_term_memory_commands():
    from app.chat import memory

    created = memory.add_memory("回答先给结论，再给依据", "preference", "test-session")
    assert created and not created.get("duplicate")
    items = memory.list_memories()
    assert any(item["content"] == "回答先给结论，再给依据" for item in items)
    assert memory.delete_memory(created["id"]) is True
    assert not any(item["id"] == created["id"] and item["active"] for item in memory.list_memories())


def test_session_model_and_effort_switch(client):
    session_id = _new_session(client)
    response = client.patch(f"/api/v1/chat/sessions/{session_id}", headers=HEADERS,
                            json={"provider_id": "deepseek", "model": "deepseek-chat",
                                  "reasoning_effort": "high", "pinned": True})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider_id"] == "deepseek"
    assert payload["model"] == "deepseek-chat"
    assert payload["reasoning_effort"] == "high"
    assert payload["pinned"] is True

    listing = client.get("/api/v1/chat/sessions", headers=HEADERS).json()["items"]
    assert listing[0]["id"] == session_id, "置顶会话应排在最前"


def test_mission_title_and_rename(client):
    created = client.post("/api/v1/missions", headers=HEADERS, json={
        "goal": "设计一颗 500km SSO 光学遥感小卫星",
        "title": "命名测试任务",
        "constraints": {"orbit_type": "SSO", "altitude_km": 500, "mass_limit_kg": 80},
    })
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
    assert detail["title"] == "命名测试任务"

    renamed = client.patch(f"/api/v1/missions/{task_id}", headers=HEADERS,
                           json={"title": "重命名后的任务"})
    assert renamed.status_code == 200
    assert client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()["title"] == "重命名后的任务"

    default = client.post("/api/v1/missions", headers=HEADERS, json={
        "goal": "设计一颗 600km SSO 通信小卫星",
        "constraints": {"orbit_type": "SSO", "altitude_km": 600, "mass_limit_kg": 80},
    }).json()["task_id"]
    assert client.get(f"/api/v1/missions/{default}", headers=HEADERS).json()["title"]


def test_chat_creates_mission_and_lists(client):
    session_id = _new_session(client)
    response = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                           json={"content": "新建任务：设计一颗 500km SSO 光学遥感小卫星"})
    assert response.status_code == 200, response.text
    meta = response.json()["assistant"]["meta"]
    assert meta.get("tool", {}).get("task_id") or "已创建任务" in response.json()["assistant"]["content"]

    listing = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                          json={"content": "查看任务列表"})
    assert listing.status_code == 200
    assert "t-" in listing.json()["assistant"]["content"]


def test_streaming_endpoint_emits_deltas(client):
    session_id = _new_session(client)
    response = client.post(f"/api/v1/chat/sessions/{session_id}/messages/stream",
                           headers=HEADERS, json={"content": "你好，介绍一下你自己"})
    assert response.status_code == 200
    text = response.text
    assert "event: delta" in text
    assert "event: done" in text
    assert "桩模式" in text


def test_kb_search_uses_sqlite_vec(client):
    from app.tools.kb import store
    from tests.seed_kb import seed as seed_kb

    seed_kb()
    result = store.search("太阳翼 电源 电池 余量", top_k=3)
    assert result["results"], "应检索到种子语料"
    assert result["index_mode"] == "sqlite-vec"
    assert result["dim_mismatch"] == 0
