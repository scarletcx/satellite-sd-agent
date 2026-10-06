"""系统接口（docs/07 §C1~C2）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.deps import require_token
from app.db import new_session
from app.providers import current_mode, models_summary, provider_status

router = APIRouter(tags=["System"])


@router.get("/healthz")
def healthz() -> dict:
    database = "ok"
    try:
        with new_session() as session:
            session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "checks": {
            "database": database,
            "embedding": "loading",  # 骨架阶段未接入（docs/12 §1）
            "llm": {"stub": current_mode() == "stub", "providers": provider_status()},
        },
    }


@router.get("/info")
def info(_: None = Depends(require_token)) -> dict:
    return {
        "app_version": "0.1.0",
        "api_version": "v1",
        "mode": current_mode(),
        "stub_mode": current_mode() == "stub",
        "models": models_summary(),
        "corpus_version": "corpus-v0.0.0",
        "template_version": "design-report-v1",
    }
