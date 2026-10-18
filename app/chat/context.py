"""上下文管理：使用量估算、自动压缩与手动 /compact。

设计（参考 Codex / Command Code）：
- 消息**全量保存**在 SQLite；发给模型的是「压缩摘要 + 最近未折叠消息」；
- 未达阈值时不做截断（不再粗暴只取最近 N 条）；
- 达到阈值百分比（设置页可配、可关闭）时，把较早消息折叠进摘要，保留最近若干条；
- 使用量为估算值（CJK 按字、英文按词），用于进度展示与阈值判断。
"""
from __future__ import annotations

import json
import re

from app.db import new_session
from app.models import AppMeta, ChatMessage, ChatSession
from app.providers import chat_json

SETTINGS_KEY = "chat_context"
DEFAULTS = {
    "auto_compact": True,
    "threshold_pct": 80,
    "default_window": 256000,   # 256k（十进制 k）：用户可在设置页按模型最大窗口调整
    "keep_recent": 6,
    "summary_max_chars": 1500,
}

_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def get_settings() -> dict:
    with new_session() as session:
        row = session.get(AppMeta, SETTINGS_KEY)
        raw = json.loads(row.value) if row and row.value else {}
    merged = {**DEFAULTS, **{key: value for key, value in raw.items() if key in DEFAULTS}}
    merged["threshold_pct"] = max(20, min(95, int(merged["threshold_pct"])))
    merged["keep_recent"] = max(2, min(30, int(merged["keep_recent"])))
    merged["default_window"] = max(8000, min(2_000_000, int(merged["default_window"])))
    merged["summary_max_chars"] = max(300, min(6000, int(merged["summary_max_chars"])))
    merged["auto_compact"] = bool(merged["auto_compact"])
    return merged


def set_settings(payload: dict) -> dict:
    current = get_settings()
    updated = {**current, **{key: value for key, value in payload.items() if key in DEFAULTS}}
    with new_session() as session:
        session.merge(AppMeta(key=SETTINGS_KEY,
                              value=json.dumps(updated, ensure_ascii=False)))
        session.commit()
    return get_settings()


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 按字、英文按词、其余按 4 字符。"""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    rest = max(0, len(text) - cjk)
    return int(cjk + words * 1.3 + rest * 0.25)


def _session_window(provider_id: str | None) -> int:
    """会话窗口以「对话与上下文」设置为准；供应商模型窗口仅作设置页参考。"""
    return int(get_settings()["default_window"])


def context_snapshot(session_id: str) -> dict:
    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is None:
            raise LookupError(f"会话不存在：{session_id}")
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id,
                        ChatMessage.id > (chat.compacted_until or 0))
                .order_by(ChatMessage.id).all())
        total = session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
        summary = chat.summary or ""
        compacted_until = chat.compacted_until or 0
        provider_id = chat.provider_id

    window = _session_window(provider_id)
    settings = get_settings()
    used = estimate_tokens(summary) + sum(estimate_tokens(row.content) for row in rows) + 120
    return {
        "window": window,
        "used_tokens": used,
        "percent": round(min(100.0, used / window * 100), 1),
        "summary_chars": len(summary),
        "compacted_until": compacted_until,
        "pending_messages": len(rows),
        "total_messages": total,
        "auto_compact": settings["auto_compact"],
        "threshold_pct": settings["threshold_pct"],
        "keep_recent": settings["keep_recent"],
    }


def compact(session_id: str, force: bool = False) -> dict:
    """把较早消息折叠进摘要；保留最近 keep_recent 条。返回压缩后的快照。"""
    settings = get_settings()
    keep_recent = int(settings["keep_recent"])
    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is None:
            raise LookupError(f"会话不存在：{session_id}")
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id,
                        ChatMessage.id > (chat.compacted_until or 0))
                .order_by(ChatMessage.id).all())
        if len(rows) <= keep_recent:
            return {**context_snapshot(session_id), "compacted_messages": 0,
                    "note": "消息不足，无需压缩"}
        fold = rows[:-keep_recent]
        history = [{"role": row.role, "content": row.content} for row in fold]
        summary = chat.summary or ""
        last_id = fold[-1].id

    payload = chat_json("CHAT_COMPACT", {
        "task_id": session_id,
        "summary": summary,
        "history": history,
        "retry_hint": "",
    })
    new_summary = str(payload.get("summary") or "").strip()[: int(settings["summary_max_chars"])]
    if not new_summary:
        new_summary = summary

    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is not None:
            chat.summary = new_summary
            chat.compacted_until = max(chat.compacted_until or 0, last_id)
            session.commit()
    snapshot = context_snapshot(session_id)
    return {**snapshot, "compacted_messages": len(history), "forced": force}


def maybe_compact(session_id: str) -> dict | None:
    settings = get_settings()
    if not settings["auto_compact"]:
        return None
    snapshot = context_snapshot(session_id)
    if (snapshot["percent"] >= settings["threshold_pct"]
            and snapshot["pending_messages"] > settings["keep_recent"]):
        return compact(session_id)
    return None


def conversation_window(session_id: str) -> tuple[str, list[dict]]:
    """返回（摘要, 未折叠消息列表）；全部消息仍在数据库，仅折叠过的不重复发送。"""
    with new_session() as session:
        chat = session.get(ChatSession, session_id)
        if chat is None:
            raise LookupError(f"会话不存在：{session_id}")
        rows = (session.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id,
                        ChatMessage.id > (chat.compacted_until or 0))
                .order_by(ChatMessage.id).all())
        return chat.summary or "", [{"role": row.role, "content": row.content} for row in rows]
