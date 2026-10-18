"""检索范围与切片规则测试：会话附件 + 全局文档可检索，过滤条件在召回阶段生效。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tools.kb import delete_document, ingest_file, search
from app.tools.kb.chunking import TARGET_CHARS, chunk_text

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    """本模块会写入全局语料，结束后清理，避免影响其他测试的检索排序。"""
    created: list[str] = []
    yield created
    for doc_id in created:
        try:
            delete_document(doc_id)
        except Exception:  # noqa: BLE001 - 清理失败不阻塞测试
            pass


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _ingest(tmp_path, name: str, text: str, *, title: str,
            session_id: str | None = None, created: list[str] | None = None) -> dict:
    extra = {"session_id": session_id} if session_id else None
    result = ingest_file(_write(tmp_path, name, text), module="other", doc_type="other",
                         license="test", title=title, extra_meta=extra)
    if created is not None:
        created.append(result["doc_id"])
    return result


def test_chunk_text_target_and_overlap():
    sentences = [f"第{i}句用于验证切片规则，长度大约二十个汉字左右。" for i in range(1, 41)]
    chunks = chunk_text("".join(sentences))
    assert len(chunks) > 1
    for piece in chunks:
        assert len(piece) <= TARGET_CHARS + int(TARGET_CHARS * 0.15) + 1
    assert chunks[1][:90] == chunks[0][-90:], "相邻块之间应保留 15% 重叠"


def test_session_search_sees_global_documents(tmp_path, _cleanup):
    query = "太阳翼面积估算"
    global_doc = _ingest(tmp_path, "global.txt", f"{query}：三结砷化镓电池、布片系数 0.85。",
                         title="全局电源资料", created=_cleanup)
    own_doc = _ingest(tmp_path, "own.txt", f"{query}：本会话上传的太阳翼面积计算说明。",
                      title="本会话附件", session_id="cs-scope-mine", created=_cleanup)
    other_doc = _ingest(tmp_path, "other.txt", f"{query}：其他会话的太阳翼资料。",
                        title="其他会话附件", session_id="cs-scope-other", created=_cleanup)

    result = search(query, filters={"session_id": "cs-scope-mine"}, top_k=5)
    doc_ids = {item["doc_id"] for item in result["results"]}
    assert global_doc["doc_id"] in doc_ids, "全局知识库文档应参与会话检索"
    assert own_doc["doc_id"] in doc_ids, "本会话附件应可检索"
    assert other_doc["doc_id"] not in doc_ids, "其他会话附件必须隔离"


def test_filtered_recall_expands_beyond_candidate_k(tmp_path, _cleanup):
    query = "姿轨控磁力矩器选型估算"
    for index in range(6):
        _ingest(tmp_path, f"filler{index}.txt", f"{query}：其他会话的填充资料 {index}。",
                title=f"填充资料 {index}", session_id="cs-filler", created=_cleanup)
    target = _ingest(tmp_path, "target.txt", f"{query}：目标文档，磁力矩器方案说明。",
                     title="目标文档", session_id="cs-target", created=_cleanup)

    result = search(query, filters={"session_id": "cs-target"}, top_k=1, candidate_k=1)
    assert [item["doc_id"] for item in result["results"]] == [target["doc_id"]], \
        "召回规模不足时应继续扩大，而不是被全局 top-k 截断"


def test_chat_cites_global_document(tmp_path, client, _cleanup):
    query = "太阳翼面积估算"
    doc = _ingest(tmp_path, "chat-global.txt",
                  f"{query}：太阳翼面积按三结砷化镓电池效率与布片系数估算。",
                  title="聊天引用全局资料", created=_cleanup)
    session_id = client.post("/api/v1/chat/sessions", headers=HEADERS, json={}).json()["id"]
    reply = client.post(f"/api/v1/chat/sessions/{session_id}/messages", headers=HEADERS,
                        json={"content": f"请检索资料：{query}"})
    assert reply.status_code == 200, reply.text
    citations = reply.json()["assistant"]["meta"]["citations"]
    assert any(item["doc_id"] == doc["doc_id"] for item in citations), \
        f"聊天应能引用全局知识库文档，实际引用：{[c['doc_id'] for c in citations]}"
