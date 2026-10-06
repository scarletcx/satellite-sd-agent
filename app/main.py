"""应用入口（docs/07 全部接口的前缀与错误模型）。

启动：uvicorn app.main:app --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import kb as kb_api
from app.api import missions, parameters, settings as settings_api, system
from app.config import settings
from app.db import init_db

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (settings.corpus_dir / "raw").mkdir(parents=True, exist_ok=True)
    (settings.corpus_dir / "synthetic").mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="AI 卫星总体设计助手 API", version="0.1.0", lifespan=lifespan)

app.include_router(system.router, prefix=API_PREFIX)
app.include_router(missions.router, prefix=API_PREFIX)
app.include_router(parameters.router, prefix=API_PREFIX)
app.include_router(kb_api.router, prefix=API_PREFIX)
app.include_router(settings_api.router, prefix=API_PREFIX)


@app.get("/")
def root() -> dict:
    return {"name": "satellite-sd-agent", "api": API_PREFIX, "docs": "/docs"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error = dict(detail)
    else:
        error = {"code": "INTERNAL", "message": str(detail), "details": {}}
    error.setdefault("details", {})
    error.setdefault("trace_id", request.headers.get("x-request-id", "req-local"))
    return JSONResponse(status_code=exc.status_code, content={"error": error})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    return JSONResponse(status_code=400, content={"error": {
        "code": "SCHEMA_INVALID",
        "message": first.get("msg", "请求体不合法"),
        "details": {"field": field},
        "trace_id": request.headers.get("x-request-id", "req-local"),
    }})
