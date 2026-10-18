"""跨会话长期记忆：用户偏好、习惯与稳定信息（不保存原始对话）。

写入途径：
- 对话自动抽取（CHAT_MEMORY，每累计 10 条消息一次）；
- `/remember <内容>` 手动写入；
- 按 id 删除（软删除 active=False）。
使用：会话的 plan / answer 提示词都会注入记忆块。
"""
from __future__ import annotations

import hashlib

from app.db import new_session
from app.models import ChatMessage, UserMemory
from app.providers import chat_json

MAX_CONTENT = 500
MAX_BLOCK_ITEMS = 20


def _digest(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()[:16]


def list_memories(active_only: bool = True) -> list[dict]:
    with new_session() as session:
        query = session.query(UserMemory)
        if active_only:
            query = query.filter(UserMemory.active.is_(True))
        rows = query.order_by(UserMemory.id.desc()).all()
        return [
            {"id": row.id, "content": row.content, "category": row.category,
             "source_session": row.source_session, "active": row.active,
             "created_at": row.created_at.isoformat() if row.created_at else None}
            for row in rows
        ]


def add_memory(content: str, category: str = "preference",
               source_session: str | None = None) -> dict | None:
    content = (content or "").strip()[:MAX_CONTENT]
    if not content:
        return None
    with new_session() as session:
        existing = (session.query(UserMemory)
                    .filter(UserMemory.active.is_(True),
                            UserMemory.content == content).first())
        if existing is not None:
            return {"id": existing.id, "content": existing.content, "duplicate": True}
        row = UserMemory(content=content, category=category[:32], source_session=source_session)
        session.add(row)
        session.commit()
        return {"id": row.id, "content": row.content, "duplicate": False}


def delete_memory(memory_id: int) -> bool:
    with new_session() as session:
        row = session.get(UserMemory, int(memory_id))
        if row is None or not row.active:
            return False
        row.active = False
        session.commit()
        return True


def memory_block(limit: int = MAX_BLOCK_ITEMS) -> str:
    items = list_memories()[:limit]
    if not items:
        return "（暂无）"
    return "\n".join(f"- [{item['category']}] {item['content']}" for item in items)


def extract_memories(session_id: str) -> int:
    """从最近消息中抽取跨会话记忆；失败不影响主流程。"""
    with new_session() as session:
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc()).limit(12).all())
        history = [{"role": row.role, "content": row.content} for row in reversed(rows)]
    if not history:
        return 0
    try:
        payload = chat_json("CHAT_MEMORY", {
            "task_id": session_id,
            "history": history,
            "existing": memory_block(),
            "retry_hint": "",
        })
    except Exception:  # noqa: BLE001 —— 记忆抽取失败不阻塞对话
        return 0
    added = 0
    for item in payload.get("memories") or []:
        content = item.get("content") if isinstance(item, dict) else str(item)
        category = item.get("category") if isinstance(item, dict) else "preference"
        result = add_memory(str(content or ""), str(category or "preference"), session_id)
        if result and not result.get("duplicate"):
            added += 1
    return added
