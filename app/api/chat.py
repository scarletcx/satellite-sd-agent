"""个人 agent 会话接口（docs/07 §D）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import api_error, require_token
from app.chat import service

router = APIRouter(prefix="/chat", tags=["Chat"])


class SessionCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class SessionRenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


def _wrap(exc: Exception) -> None:
    message = str(exc)
    if isinstance(exc, service.ChatError):
        if "不存在" in message:
            api_error(404, "CHAT_NOT_FOUND", message)
        api_error(400, "CHAT_INVALID", message)
    raise exc


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
def rename_session(session_id: str, body: SessionRenameBody,
                   _: None = Depends(require_token)) -> dict:
    try:
        return service.rename_session(session_id, body.title)
    except service.ChatError as exc:
        _wrap(exc)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, _: None = Depends(require_token)) -> dict:
    try:
        return service.delete_session(session_id)
    except service.ChatError as exc:
        _wrap(exc)


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, limit: int = Query(default=300, ge=1, le=1000),
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
