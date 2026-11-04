"""公式管理接口：查看、试算、编辑、重置与版本历史。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import api_error, require_token
from app.services import formulas as formula_service
from app.tools.calc.formula_engine import FormulaError

router = APIRouter(tags=["Formulas"])


class FormulaUpdateBody(BaseModel):
    expression: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=2000)
    updated_by: str = Field(default="engineer", max_length=64)


class FormulaPreviewBody(BaseModel):
    context: dict[str, float] | None = None


class FormulaResetBody(BaseModel):
    updated_by: str = Field(default="engineer", max_length=64)


def _handle_error(exc: FormulaError, formula_id: str | None = None):
    message = str(exc)
    if "不存在" in message:
        api_error(404, "FORMULA_NOT_FOUND", message, {"formula_id": formula_id})
    api_error(400, "FORMULA_INVALID", message, {"formula_id": formula_id})


@router.get("/formulas/constants")
def formula_constants(_: None = Depends(require_token)) -> dict:
    return {"items": formula_service.formula_constants()}


@router.get("/formulas")
def list_formulas(tool: str | None = Query(default=None),
                  category: str | None = Query(default=None),
                  _: None = Depends(require_token)) -> dict:
    items = formula_service.list_formulas(tool=tool, category=category)
    return {"items": items, "total": len(items)}


@router.get("/formulas/{formula_id}")
def get_formula(formula_id: str, _: None = Depends(require_token)) -> dict:
    try:
        return formula_service.get_formula(formula_id)
    except FormulaError as exc:
        _handle_error(exc, formula_id)


@router.put("/formulas/{formula_id}")
def update_formula(formula_id: str, body: FormulaUpdateBody,
                   _: None = Depends(require_token)) -> dict:
    try:
        return formula_service.update_formula(
            formula_id, body.expression, body.description, body.updated_by)
    except FormulaError as exc:
        _handle_error(exc, formula_id)


@router.post("/formulas/{formula_id}/reset")
def reset_formula(formula_id: str, body: FormulaResetBody | None = None,
                  _: None = Depends(require_token)) -> dict:
    try:
        return formula_service.reset_formula(
            formula_id, (body.updated_by if body else "engineer"))
    except FormulaError as exc:
        _handle_error(exc, formula_id)


@router.post("/formulas/{formula_id}/preview")
def preview_formula(formula_id: str, body: FormulaPreviewBody | None = None,
                    _: None = Depends(require_token)) -> dict:
    try:
        return formula_service.preview_formula(
            formula_id, body.context if body else None)
    except FormulaError as exc:
        _handle_error(exc, formula_id)
