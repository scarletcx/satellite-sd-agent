"""个人 agent 会话服务：SQLite 记忆（短期消息 + 长期摘要）+ LangGraph 编排。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.chat.graph import run_agent
from app.db import new_session
from app.models import ChatDocument, ChatMessage, ChatSession
from app.orchestrator.ids import next_chat_document_id, next_chat_session_id
from app.providers import chat_json
from app.tools.kb import store as kb_store

SHORT_TERM_LIMIT = 12          # 每次请求带上的最近消息数
SUMMARY_EVERY = 10             # 每累计 10 条消息刷新一次长期摘要
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _session_dict(row: ChatSession, message_count: int = 0, last_message: str = "") -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
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
                .order_by(ChatSession.updated_at.desc())
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
        return {**_session_dict(row, count), "documents": [_document_dict(item) for item in documents]}


def rename_session(session_id: str, title: str) -> dict:
    with new_session() as session:
        row = _require_session(session, session_id)
        row.title = title.strip()[:120] or row.title
        session.commit()
        return _session_dict(row)


def delete_session(session_id: str) -> dict:
    with new_session() as session:
        _require_session(session, session_id)
        documents = (session.query(ChatDocument)
                     .filter(ChatDocument.session_id == session_id).all())
        doc_ids = [item.doc_id for item in documents]
        session.query(ChatDocument).filter(ChatDocument.session_id == session_id).delete()
        messages = (session.query(ChatMessage)
                    .filter(ChatMessage.session_id == session_id).delete())
        session.delete(session.get(ChatSession, session_id))
        session.commit()

    removed_docs = 0
    for doc_id in doc_ids:
        try:
            kb_store.delete_document(doc_id, reviewer="chat-session-delete")
            removed_docs += 1
        except Exception:  # noqa: BLE001 —— 附件可能已被单独删除
            continue
    return {"session_id": session_id, "deleted_messages": messages, "deleted_documents": removed_docs}


def list_messages(session_id: str, limit: int = 300) -> dict:
    with new_session() as session:
        _require_session(session, session_id)
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id)
                .limit(limit).all())
        return {"items": [_message_dict(row) for row in rows], "total": len(rows)}


def post_message(session_id: str, content: str) -> dict:
    content = content.strip()
    if not content:
        raise ChatError("消息不能为空")

    with new_session() as session:
        chat = _require_session(session, session_id)
        user_row = ChatMessage(session_id=session_id, role="user", content=content)
        session.add(user_row)
        if chat.title in ("", "新会话"):
            chat.title = content.splitlines()[0][:40]
        chat.updated_at = _now()
        session.commit()
        session.refresh(user_row)
        user_message = _message_dict(user_row)

        history_rows = (session.query(ChatMessage)
                        .filter(ChatMessage.session_id == session_id)
                        .order_by(ChatMessage.id.desc())
                        .limit(SHORT_TERM_LIMIT).all())
        history = [{"role": row.role, "content": row.content}
                   for row in reversed(history_rows)]
        summary = chat.summary or ""

    from app.providers.base import ProviderError

    try:
        result = run_agent(session_id, content, history, summary)
    except ProviderError as exc:
        result = {
            "answer": f"模型服务暂不可用：{exc}。请到「设置」页检查供应商与模型配置后重试。",
            "citations": [], "used_citations": [],
            "plan": {"action": "error"}, "index_mode": None,
        }
    answer = str(result.get("answer") or "").strip()
    if not answer:
        answer = "（没有生成有效回答，请重试或检查模型设置。）"
    citations = result.get("citations") or []
    used = set(result.get("used_citations") or [])
    if used:
        citations = [item for item in citations if item.get("id") in used] or citations

    with new_session() as session:
        assistant_row = ChatMessage(
            session_id=session_id, role="assistant", content=answer,
            meta={
                "citations": citations,
                "used_citations": sorted(used),
                "action": (result.get("plan") or {}).get("action"),
                "index_mode": result.get("index_mode"),
            },
        )
        session.add(assistant_row)
        chat = session.get(ChatSession, session_id)
        chat.updated_at = _now()
        session.commit()
        session.refresh(assistant_row)
        assistant_message = _message_dict(assistant_row)
        total = session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()

    if total and total % SUMMARY_EVERY == 0:
        _refresh_summary(session_id)

    return {"user": user_message, "assistant": assistant_message,
            "session": get_session(session_id)}


def _refresh_summary(session_id: str) -> str:
    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is None:
            return ""
        summary = chat.summary or ""
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(SHORT_TERM_LIMIT).all())
        history = [{"role": row.role, "content": row.content} for row in reversed(rows)]
    try:
        payload = chat_json("CHAT_SUMMARY", {
            "task_id": session_id,
            "summary": summary,
            "history": history,
            "retry_hint": "",
        })
        updated = str(payload.get("summary") or "").strip()
    except Exception:  # noqa: BLE001 —— 摘要失败不影响本轮对话
        return summary
    if updated:
        with new_session() as session:
            chat = session.get(ChatSession, session_id)
            if chat is not None:
                chat.summary = updated[:1000]
                session.commit()
    return updated or summary


def upload_document(session_id: str, filename: str, data: bytes) -> dict:
    with new_session() as session:
        _require_session(session, session_id)

    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ChatError(f"不支持的文件类型：{suffix or '未知'}（支持 pdf/docx/txt/md/csv）")
    if len(data) == 0:
        raise ChatError("文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ChatError(f"文件过大（>{MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")

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
            chunks=result["chunks"],
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
        session.delete(link)
        session.commit()
    try:
        kb_store.delete_document(doc_id, reviewer="chat-document-delete")
    except Exception:  # noqa: BLE001
        pass
    return {"document_id": document_id, "doc_id": doc_id}
