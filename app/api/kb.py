"""知识库接口（docs/07 §B1~B5）。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import api_error, require_token
from app.config import settings
from app.tools import kb
from app.tools.kb.store import KbError

router = APIRouter(tags=["KnowledgeBase"])


class KBSearchFilters(BaseModel):
    module: str | None = None
    doc_type: str | None = None
    year_from: int | None = Field(default=None, ge=1950)
    is_synthetic: bool = True


class KBSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    filters: KBSearchFilters | None = None
    top_k: int = Field(default=8, ge=1, le=20)


@router.post("/kb/search")
def kb_search(body: KBSearchRequest, _: None = Depends(require_token)) -> dict:
    filters = body.filters.model_dump(exclude_none=True) if body.filters else {}
    return kb.search(body.query, filters=filters, top_k=body.top_k)


@router.post("/kb/ingest", status_code=201)
async def kb_ingest(
    file: UploadFile = File(...),
    module: str = Form(...),
    doc_type: str = Form(...),
    license: str = Form(...),
    is_synthetic: bool = Form(default=False),
    title: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    _: None = Depends(require_token),
) -> dict:
    target_dir = settings.corpus_dir / "raw" / module
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", Path(file.filename or "upload").name)
    target = target_dir / safe_name
    target.write_bytes(await file.read())

    try:
        return kb.ingest_file(
            target, module=module, doc_type=doc_type, license=license,
            is_synthetic=is_synthetic, title=title, source_url=source_url,
        )
    except KbError as exc:
        message = str(exc)
        duplicated = "已存在" in message
        api_error(409 if duplicated else 400,
                  "STATE_CONFLICT" if duplicated else "SCHEMA_INVALID", message)


@router.get("/kb/documents")
def kb_documents(module: str | None = Query(default=None), doc_type: str | None = Query(default=None),
                 page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                 _: None = Depends(require_token)) -> dict:
    return kb.list_documents(module=module, doc_type=doc_type, page=page, page_size=page_size)


@router.delete("/kb/documents/{doc_id}")
def kb_delete(doc_id: str, confirm: bool = Query(default=False),
              _: None = Depends(require_token)) -> dict:
    if not confirm:
        api_error(400, "SCHEMA_INVALID", "删除语料需要 confirm=true", {"field": "confirm"})
    try:
        return kb.delete_document(doc_id)
    except KbError as exc:
        api_error(404, "DOC_NOT_FOUND", str(exc))


@router.get("/kb/stats")
def kb_stats(_: None = Depends(require_token)) -> dict:
    return kb.stats()
