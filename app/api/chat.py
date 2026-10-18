"""个人 agent 会话接口（docs/07 §D）。"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import api_error, require_token
from app.chat import context as chat_context_store
from app.chat import service
from app.providers.base import ProviderError

router = APIRouter(prefix="/chat", tags=["Chat"])


class SessionCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class SessionUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None
    provider_id: str | None = None
    model: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


def _wrap(exc: Exception) -> None:
    message = str(exc)
    if isinstance(exc, service.ChatError):
        if "不存在" in message:
            api_error(404, "CHAT_NOT_FOUND", message)
        api_error(400, "CHAT_INVALID", message)
    raise exc


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _async_chunks(iterator):
    """把同步生成器（模型流式/分块）转成异步流，避免阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def worker() -> None:
        try:
            for item in iterator:
                loop.call_soon_threadsafe(queue.put_nowait, ("data", item))
            loop.call_soon_threadsafe(queue.put_nowait, ("end", None))
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, value = await queue.get()
        if kind == "end":
            return
        if kind == "error":
            raise value
        yield value


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreateBody | None = None, _: None = Depends(require_token)) -> dict:
    return service.create_session(body.title if body else None)


@router.get("/sessions")
def list_sessions(limit: int = Query(default=100, ge=1, le=200),
                  _: None = Depends(require_token)) -> dict:
    return service.list_sessions(limit=limit)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, _: None = Depends(require_token)) -> dict:
    try:
        return service.get_session(session_id)
    except service.ChatError as exc:
        _wrap(exc)


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, body: SessionUpdateBody,
                   _: None = Depends(require_token)) -> dict:
    try:
        payload = body.model_dump(exclude_unset=True)
        return service.update_session(session_id, payload)
    except service.ChatError as exc:
        _wrap(exc)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, _: None = Depends(require_token)) -> dict:
    try:
        return service.delete_session(session_id)
    except service.ChatError as exc:
        _wrap(exc)


@router.get("/sessions/{session_id}/context")
def get_context(session_id: str, _: None = Depends(require_token)) -> dict:
    try:
        return chat_context_store.context_snapshot(session_id)
    except LookupError as exc:
        _wrap(service.ChatError(str(exc)))


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, limit: int = Query(default=1000, ge=1, le=2000),
                  _: None = Depends(require_token)) -> dict:
    try:
        return service.list_messages(session_id, limit=limit)
    except service.ChatError as exc:
        _wrap(exc)


@router.post("/sessions/{session_id}/messages")
def post_message(session_id: str, body: MessageBody,
                 _: None = Depends(require_token)) -> dict:
    try:
        return service.post_message(session_id, body.content)
    except service.ChatError as exc:
        _wrap(exc)


@router.post("/sessions/{session_id}/messages/stream")
async def post_message_stream(session_id: str, body: MessageBody,
                              _: None = Depends(require_token)):
    """SSE 流式对话：user → delta… → done（逐字渲染）。"""
    try:
        prepared = service.prepare_turn(session_id, body.content, streaming=True)
    except service.ChatError as exc:
        _wrap(exc)

    async def generator():
        yield _sse("user", prepared["user"])
        collected: list[str] = []
        try:
            async for chunk in _async_chunks(service.stream_answer_chunks(prepared)):
                collected.append(chunk)
                yield _sse("delta", {"text": chunk})
        except ProviderError as exc:
            text = f"模型流式输出失败：{exc}。请检查设置页的供应商与模型。"
            collected.append(text)
            yield _sse("delta", {"text": text})
        except Exception as exc:  # noqa: BLE001
            text = f"生成回答失败：{exc}"
            collected.append(text)
            yield _sse("delta", {"text": text})

        text = "".join(collected)
        used = service.extract_used_citations(text)
        try:
            result = service.finish_turn(prepared, text,
                                         used_citations=used or None)
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": f"保存消息失败：{exc}"})
            return
        yield _sse("done", result)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}/documents")
def list_documents(session_id: str, _: None = Depends(require_token)) -> dict:
    try:
        detail = service.get_session(session_id)
    except service.ChatError as exc:
        _wrap(exc)
    return {"items": detail["documents"], "total": len(detail["documents"])}


@router.post("/sessions/{session_id}/documents", status_code=201)
async def upload_document(session_id: str, file: UploadFile = File(...),
                          _: None = Depends(require_token)) -> dict:
    data = await file.read()
    try:
        return service.upload_document(session_id, file.filename or "upload", data)
    except service.ChatError as exc:
        _wrap(exc)


@router.delete("/sessions/{session_id}/documents/{document_id}")
def delete_document(session_id: str, document_id: str,
                    _: None = Depends(require_token)) -> dict:
    try:
        return service.delete_document(session_id, document_id)
    except service.ChatError as exc:
        _wrap(exc)

