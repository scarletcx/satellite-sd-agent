"""个人 agent 会话服务：SQLite 记忆（全量消息 + 压缩摘要 + 跨会话记忆）+ LangGraph 编排。"""
from __future__ import annotations

import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.chat import commands as commands_store
from app.chat import context as context_store
from app.chat import memory as memory_store
from app.chat.graph import run_agent
from app.config import settings
from app.db import new_session
from app.models import ChatDocument, ChatMessage, ChatSession
from app.orchestrator.ids import next_chat_document_id, next_chat_session_id
from app.providers import stream_text
from app.providers.base import ProviderError
from app.providers.specs import find_spec, load_specs
from app.tools.kb import store as kb_store

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MEMORY_EVERY = 10
_CITATION_RE = re.compile(r"S\d+")


class ChatError(LookupError):
    """会话/附件业务错误（API 映射为 404/400）。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message_dict(row: ChatMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "meta": dict(row.meta or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _document_dict(row: ChatDocument) -> dict:
    return {
        "id": row.id,
        "doc_id": row.doc_id,
        "filename": row.filename,
        "chunks": row.chunks,
        "scope": row.scope or "session",
        "kind": row.kind or "document",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _session_dict(row: ChatSession, message_count: int = 0, last_message: str = "") -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "pinned": bool(row.pinned),
        "provider_id": row.provider_id,
        "model": row.model,
        "reasoning_effort": row.reasoning_effort,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "message_count": message_count,
        "last_message": last_message,
    }


def create_session(title: str | None = None) -> dict:
    with new_session() as session:
        session_id = next_chat_session_id(session)
        row = ChatSession(id=session_id, title=(title or "新会话").strip()[:120] or "新会话")
        session.add(row)
        session.commit()
        return _session_dict(row)


def list_sessions(limit: int = 100) -> dict:
    with new_session() as session:
        rows = (session.query(ChatSession)
                .filter(ChatSession.archived.is_(False))
                .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
                .limit(limit).all())
        items = []
        for row in rows:
            count = session.query(ChatMessage).filter(ChatMessage.session_id == row.id).count()
            last = (session.query(ChatMessage).filter(ChatMessage.session_id == row.id)
                    .order_by(ChatMessage.id.desc()).first())
            items.append(_session_dict(row, count, (last.content[:80] if last else "")))
    return {"items": items, "total": len(items)}


def _require_session(session, session_id: str) -> ChatSession:
    row = session.get(ChatSession, session_id)
    if row is None:
        raise ChatError(f"会话不存在：{session_id}")
    return row


def get_session(session_id: str) -> dict:
    with new_session() as session:
        row = _require_session(session, session_id)
        count = session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
        documents = (session.query(ChatDocument)
                     .filter(ChatDocument.session_id == session_id)
                     .order_by(ChatDocument.id).all())
        return {**_session_dict(row, count),
                "documents": [_document_dict(item) for item in documents],
                "context": context_store.context_snapshot(session_id)}


def update_session(session_id: str, payload: dict) -> dict:
    with new_session() as session:
        row = _require_session(session, session_id)
        if "title" in payload and payload["title"] is not None:
            row.title = str(payload["title"]).strip()[:120] or row.title
        if "pinned" in payload and payload["pinned"] is not None:
            row.pinned = bool(payload["pinned"])
        if "provider_id" in payload:
            provider_id = payload["provider_id"] or None
            if provider_id and find_spec(provider_id) is None:
                raise ChatError(f"供应商不存在：{provider_id}")
            row.provider_id = provider_id
        if "model" in payload:
            row.model = (str(payload["model"]).strip()[:120] or None) if payload["model"] else None
        if "reasoning_effort" in payload:
            effort = payload["reasoning_effort"] or None
            if effort is not None and effort not in ("low", "medium", "high"):
                raise ChatError("推理强度可选：low / medium / high")
            row.reasoning_effort = effort
        row.updated_at = _now()
        session.commit()
        return _session_dict(row)


def rename_session(session_id: str, title: str) -> dict:
    return update_session(session_id, {"title": title})


def delete_session(session_id: str) -> dict:
    with new_session() as session:
        _require_session(session, session_id)
        documents = (session.query(ChatDocument)
                     .filter(ChatDocument.session_id == session_id).all())
        doc_ids = [item.doc_id for item in documents if (item.kind or "document") == "document"]
        session.query(ChatDocument).filter(ChatDocument.session_id == session_id).delete()
        messages = (session.query(ChatMessage)
                    .filter(ChatMessage.session_id == session_id).delete())
        session.delete(session.get(ChatSession, session_id))
        session.commit()
    removed = 0
    for doc_id in doc_ids:
        try:
            kb_store.delete_document(doc_id, reviewer="chat-session-delete")
            removed += 1
        except Exception:  # noqa: BLE001
            continue
    return {"session_id": session_id, "deleted_messages": messages, "deleted_documents": removed}


def list_messages(session_id: str, limit: int = 1000) -> dict:
    with new_session() as session:
        _require_session(session, session_id)
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id)
                .limit(limit).all())
        return {"items": [_message_dict(row) for row in rows], "total": len(rows)}


# ---------------------------------------------------------------- 一轮对话


def _provider_options(chat: ChatSession) -> dict:
    return {
        "provider_id": chat.provider_id,
        "model": chat.model,
        "reasoning_effort": chat.reasoning_effort,
    }


def _insert_message(session_id: str, role: str, content: str, meta: dict | None = None) -> dict:
    with new_session() as session:
        row = ChatMessage(session_id=session_id, role=role, content=content, meta=meta or {})
        session.add(row)
        chat = session.get(ChatSession, session_id)
        if chat is not None:
            chat.updated_at = _now()
            if role == "user" and chat.title in ("", "新会话"):
                chat.title = content.strip().splitlines()[0][:40] or chat.title
        session.commit()
        session.refresh(row)
        return _message_dict(row)


def prepare_turn(session_id: str, content: str, *, streaming: bool = False) -> dict:
    content = (content or "").strip()
    if not content:
        raise ChatError("消息不能为空")
    user_message = _insert_message(session_id, "user", content)

    compaction = context_store.maybe_compact(session_id)
    summary, history = context_store.conversation_window(session_id)
    if history and history[-1]["role"] == "user" and history[-1]["content"] == content:
        history = history[:-1]

    with new_session() as session:
        chat = _require_session(session, session_id)
        options = _provider_options(chat)

    try:
        state = run_agent(session_id, content, history, summary,
                          memory_store.memory_block(), options, streaming=streaming)
    except ProviderError as exc:
        state = {
            "answer": f"模型服务暂不可用：{exc}。请到「设置」页检查供应商与模型配置后重试。",
            "plan": {"action": "error"}, "citations": [],
        }
    return {
        "session_id": session_id,
        "content": content,
        "user": user_message,
        "state": state,
        "history": history,
        "summary": summary,
        "options": options,
        "context": context_store.context_snapshot(session_id),
        "compaction": compaction,
    }


def answer_text(state: dict) -> str:
    plan = state.get("plan") or {}
    if plan.get("action") == "answer" and plan.get("answer"):
        return str(plan["answer"])
    return str(state.get("answer") or "")


def finish_turn(prepared: dict, answer: str, *, used_citations: list[str] | None = None,
                extra: dict | None = None) -> dict:
    session_id = prepared["session_id"]
    state = prepared["state"]
    plan = state.get("plan") or {}
    citations = state.get("citations") or []
    used = used_citations if used_citations is not None else list(state.get("used_citations") or [])
    if used:
        citations = [item for item in citations if item.get("id") in set(used)] or citations

    meta = {
        "citations": citations,
        "used_citations": used,
        "action": plan.get("action"),
        "index_mode": state.get("index_mode"),
        "tool": state.get("tool_result") or (extra or {}).get("tool"),
        "compaction": prepared.get("compaction"),
    }
    assistant = _insert_message(session_id, "assistant", answer, meta)

    with new_session() as session:
        total = session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
    if total and total % MEMORY_EVERY == 0:
        memory_store.extract_memories(session_id)

    return {
        "user": prepared["user"],
        "assistant": assistant,
        "session": get_session(session_id),
        "context": context_store.context_snapshot(session_id),
    }


def stream_answer_chunks(prepared: dict):
    """逐块产出回答文本（工具/直答走分块，检索回答走模型流式）。"""
    state = prepared["state"]
    plan = state.get("plan") or {}
    if state.get("tool_result") is not None or (plan.get("action") == "answer" and plan.get("answer")):
        text = answer_text(state)
        step = 6
        for index in range(0, len(text), step):
            yield text[index:index + step]
        return
    context = {
        "task_id": prepared["session_id"],
        "provider_id": prepared["options"].get("provider_id"),
        "question": prepared["content"],
        "history": prepared["history"],
        "summary": prepared["summary"],
        "memories": memory_store.memory_block(),
        "evidence": state.get("citations") or [],
    }
    yield from stream_text("CHAT_ANSWER_STREAM", context, options=prepared["options"])


def post_message(session_id: str, content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise ChatError("消息不能为空")

    if commands_store.is_command(content):
        user_message = _insert_message(session_id, "user", content)
        try:
            result = commands_store.execute(session_id, content)
        except Exception as exc:  # noqa: BLE001
            result = {"content": f"命令执行失败：{exc}", "meta": {"command": "error"}}
        assistant = _insert_message(session_id, "assistant", result["content"],
                                    {**result.get("meta", {}), "command": True})
        return {"user": user_message, "assistant": assistant,
                "session": get_session(session_id),
                "context": context_store.context_snapshot(session_id)}

    prepared = prepare_turn(session_id, content)
    return finish_turn(prepared, answer_text(prepared["state"]))


def extract_used_citations(text: str) -> list[str]:
    return sorted(set(_CITATION_RE.findall(text or "")))


# ---------------------------------------------------------------- 附件


def _image_path(session_id: str, filename: str) -> Path:
    directory = Path(settings.artifacts_dir) / "chat" / session_id
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", filename or "image")
    return directory / f"{uuid.uuid4().hex[:8]}-{safe}"


def upload_document(session_id: str, filename: str, data: bytes) -> dict:
    with new_session() as session:
        _require_session(session, session_id)

    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES and suffix not in IMAGE_SUFFIXES:
        raise ChatError(f"不支持的文件类型：{suffix or '未知'}（支持 pdf/docx/txt/md/csv 与图片）")
    if not data:
        raise ChatError("文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ChatError(f"文件过大（>{MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")

    if suffix in IMAGE_SUFFIXES:
        target = _image_path(session_id, filename)
        target.write_bytes(data)
        with new_session() as session:
            link = ChatDocument(
                id=next_chat_document_id(session, session_id),
                session_id=session_id, doc_id=f"image-{target.stem[:12]}",
                filename=filename or target.name, chunks=0, scope="session", kind="image",
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return _document_dict(link)

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(data)
        temp_path = Path(handle.name)
    try:
        try:
            result = kb_store.ingest_file(
                temp_path, module="other", doc_type="other", license="user-upload",
                is_synthetic=False, title=filename,
                extra_meta={"session_id": session_id},
            )
        except kb_store.KbError as exc:
            raise ChatError(str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    with new_session() as session:
        link = ChatDocument(
            id=next_chat_document_id(session, session_id),
            session_id=session_id, doc_id=result["doc_id"], filename=filename,
            chunks=result["chunks"], scope="session", kind="document",
        )
        session.add(link)
        chat = session.get(ChatSession, session_id)
        if chat is not None:
            chat.updated_at = _now()
        session.commit()
        session.refresh(link)
        return _document_dict(link)


def delete_document(session_id: str, document_id: str) -> dict:
    with new_session() as session:
        _require_session(session, session_id)
        link = (session.query(ChatDocument)
                .filter(ChatDocument.id == document_id,
                        ChatDocument.session_id == session_id).first())
        if link is None:
            raise ChatError(f"附件不存在：{document_id}")
        doc_id = link.doc_id
        kind = link.kind
        session.delete(link)
        session.commit()
    if (kind or "document") == "document":
        try:
            kb_store.delete_document(doc_id, reviewer="chat-document-delete")
        except Exception:  # noqa: BLE001
            pass
    return {"document_id": document_id, "doc_id": doc_id}
