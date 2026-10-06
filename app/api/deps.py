"""API 公共依赖：认证与错误（docs/07 §1.2/§1.5）。"""
from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.app_token}"
    if not authorization or authorization.strip() != expected:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "无效的访问令牌", "details": {}},
        )


def api_error(status_code: int, code: str, message: str, details: dict | None = None):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or {}},
    )
