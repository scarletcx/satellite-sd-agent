"""个人 agent 会话测试（SQLite 记忆 + LangGraph 编排 + 会话附件检索）。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_session_lifecycle(client):
    created = client.post("/api/v1/chat/sessions", headers=HEADERS, json={"title": "测试会话"})
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert session_id.startswith("cs-")

    listing = client.get("/api/v1/chat/sessions", headers=HEADERS).json()
    assert any(item["id"] == session_id for item in listing["items"])

    renamed = client.patch(f"/api/v1/chat/sessions/{session_id}", headers=HEADERS,
                           json={"title": "重命名会话"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "重命名会话"

    detail = client.get(f"/api/v1/chat/sessions/{session_id}", headers=HEADERS).json()
    assert detail["title"] == "重命名会话"
    assert detail["documents"] == []

    deleted = client.delete(f"/api/v1/chat/sessions/{session_id}", headers=HEADERS)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/chat/sessions/{session_id}", headers=HEADERS).status_code == 404


def test_chat_message_roundtrip_and_isolation(client):
    first = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]
    second = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]

    sent = client.post(f"/api/v1/chat/sessions/{first}/messages", headers=HEADERS,
                       json={"content": "你好，先介绍一下你自己"})
    assert sent.status_code == 200, sent.text
    payload = sent.json()
    assert payload["user"]["role"] == "user"
    assert payload["assistant"]["role"] == "assistant"
    assert payload["assistant"]["content"]
    assert payload["session"]["title"] != "新会话", "首条消息应自动作为会话标题"

    messages = client.get(f"/api/v1/chat/sessions/{first}/messages", headers=HEADERS).json()
    assert messages["total"] == 2

    other = client.get(f"/api/v1/chat/sessions/{second}/messages", headers=HEADERS).json()
    assert other["total"] == 0, "多会话消息必须隔离"


def test_upload_document_and_retrieve_in_chat(client):
    session_id = client.post("/api/v1/chat/sessions", headers=HEADERS,
                             json={"title": "资料检索"}).json()["id"]
    content = ("CubeSat 设计要点：结构质量预算建议留 20% 余量；"
               "测控链路余量不低于 3 dB。")
    uploaded = client.post(
        f"/api/v1/chat/sessions/{session_id}/documents",
        headers=HEADERS,
        files={"file": ("cube-notes.txt", content.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["chunks"] >= 1

    reply = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                        json={"content": "请检索资料：链路余量要求是多少？"})
    assert reply.status_code == 200, reply.text
    meta = reply.json()["assistant"]["meta"]
    assert meta["action"] == "search"
    assert meta["citations"], "应检索到已上传资料"
    assert meta["citations"][0]["title"] == "cube-notes.txt"
    assert meta["index_mode"] in ("sqlite-vec", "scan")

    documents = client.get(f"/api/v1/chat/sessions/{session_id}/documents", headers=HEADERS).json()
    assert documents["total"] == 1

    removed = client.delete(
        f"/api/v1/chat/sessions/{session_id}/documents/{document['id']}", headers=HEADERS)
    assert removed.status_code == 200
    assert client.get(f"/api/v1/chat/sessions/{session_id}/documents",
                      headers=HEADERS).json()["total"] == 0


def test_upload_rejects_unsupported_type(client):
    session_id = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/documents",
        headers=HEADERS,
        files={"file": ("binary.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHAT_INVALID"
