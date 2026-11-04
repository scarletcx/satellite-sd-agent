"""公式库服务：默认定义、版本管理、安全试算与计算覆盖。"""
from __future__ import annotations

import logging

from app.db import new_session
from app.models import FormulaDefinition, FormulaVersion
from app.tools.calc.formula_engine import (
    CONSTANT_META,
    CONSTANTS,
    FormulaError,
    evaluate,
)
from app.tools.calc.constants import FORMULA_VERSIONS
from app.tools.calc.formulas import DEFAULT_BY_ID, DEFAULT_FORMULAS

logger = logging.getLogger(__name__)


def _serialize(row: FormulaDefinition) -> dict:
    default = DEFAULT_BY_ID.get(row.id, {})
    return {
        "id": row.id,
        "tool": row.tool,
        "output_key": row.output_key,
        "category": row.category,
        "name": row.name,
        "description": row.description or "",
        "expression": row.expression,
        "default_expression": default.get("expression", ""),
        "variables": list(row.variables or []),
        "sample_context": dict(row.sample_context or {}),
        "unit": row.unit or "",
        "version": row.version,
        "is_custom": bool(row.is_custom),
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def ensure_defaults() -> None:
    """补齐默认公式；不覆盖已有自定义版本。"""
    with new_session() as session:
        created = False
        for spec in DEFAULT_FORMULAS:
            if session.get(FormulaDefinition, spec["id"]) is not None:
                continue
            row = FormulaDefinition(
                id=spec["id"], tool=spec["tool"], output_key=spec["output_key"],
                category=spec["category"], name=spec["name"],
                description=spec.get("description", ""), expression=spec["expression"],
                variables=spec.get("variables", []),
                sample_context=spec.get("sample_context", {}),
                unit=spec.get("unit", ""), version=1, is_custom=False,
                updated_by="system",
            )
            session.add(row)
            session.add(FormulaVersion(
                formula_id=spec["id"], version=1, expression=spec["expression"],
                description=spec.get("description", ""), updated_by="system",
            ))
            created = True
        if created:
            session.commit()


def list_formulas(tool: str | None = None, category: str | None = None) -> list[dict]:
    ensure_defaults()
    with new_session() as session:
        query = session.query(FormulaDefinition)
        if tool:
            query = query.filter(FormulaDefinition.tool == tool)
        if category:
            query = query.filter(FormulaDefinition.category == category)
        rows = query.order_by(FormulaDefinition.category,
                              FormulaDefinition.tool,
                              FormulaDefinition.id).all()
        return [_serialize(row) for row in rows]


def get_formula(formula_id: str) -> dict:
    ensure_defaults()
    with new_session() as session:
        row = session.get(FormulaDefinition, formula_id)
        if row is None:
            raise FormulaError(f"公式不存在：{formula_id}")
        data = _serialize(row)
        history = (session.query(FormulaVersion)
                   .filter(FormulaVersion.formula_id == formula_id)
                   .order_by(FormulaVersion.version.desc()).limit(20).all())
        data["history"] = [
            {"version": item.version, "expression": item.expression,
             "updated_by": item.updated_by,
             "updated_at": item.created_at.isoformat() if item.created_at else None}
            for item in history
        ]
        return data


def preview_formula(formula_id: str, context: dict | None = None) -> dict:
    ensure_defaults()
    with new_session() as session:
        row = session.get(FormulaDefinition, formula_id)
        if row is None:
            raise FormulaError(f"公式不存在：{formula_id}")
        merged = {**dict(row.sample_context or {}), **(context or {})}
        value = evaluate(row.expression, merged)
        return {"formula_id": formula_id, "expression": row.expression,
                "context": merged, "value": value}


def update_formula(formula_id: str, expression: str, description: str | None = None,
                   updated_by: str = "engineer") -> dict:
    ensure_defaults()
    expression = (expression or "").strip()
    if not expression:
        raise FormulaError("公式不能为空")
    with new_session() as session:
        row = session.get(FormulaDefinition, formula_id)
        if row is None:
            raise FormulaError(f"公式不存在：{formula_id}")
        evaluate(expression, dict(row.sample_context or {}))
        default = DEFAULT_BY_ID.get(formula_id, {})
        row.expression = expression
        if description is not None:
            row.description = description.strip()
        row.version += 1
        row.is_custom = expression != (default.get("expression") or "").strip()
        row.updated_by = updated_by or "engineer"
        session.add(FormulaVersion(
            formula_id=formula_id, version=row.version, expression=row.expression,
            description=row.description or "", updated_by=row.updated_by,
        ))
        session.commit()
        return _serialize(row)


def reset_formula(formula_id: str, updated_by: str = "engineer") -> dict:
    ensure_defaults()
    default = DEFAULT_BY_ID.get(formula_id)
    if default is None:
        raise FormulaError(f"公式不存在：{formula_id}")
    with new_session() as session:
        row = session.get(FormulaDefinition, formula_id)
        if row is None:
            raise FormulaError(f"公式不存在：{formula_id}")
        row.expression = default["expression"]
        row.description = default.get("description", "")
        row.version += 1
        row.is_custom = False
        row.updated_by = updated_by or "engineer"
        session.add(FormulaVersion(
            formula_id=formula_id, version=row.version, expression=row.expression,
            description=row.description or "", updated_by=row.updated_by,
        ))
        session.commit()
        return _serialize(row)


def overrides_for_tool(tool: str) -> dict[str, str]:
    ensure_defaults()
    with new_session() as session:
        rows = (session.query(FormulaDefinition)
                .filter(FormulaDefinition.tool == tool,
                        FormulaDefinition.is_custom.is_(True)).all())
        return {row.output_key: row.expression for row in rows}


def apply_overrides(tool: str, context: dict) -> dict[str, float]:
    """按默认定义顺序应用自定义公式（后续公式能看到前面被覆盖的值）。"""
    overrides = overrides_for_tool(tool)
    if not overrides:
        return {}
    ctx = dict(context)
    updates: dict[str, float] = {}
    for spec in DEFAULT_FORMULAS:
        if spec["tool"] != tool:
            continue
        expression = overrides.get(spec["output_key"])
        if not expression:
            continue
        try:
            value = evaluate(expression, ctx)
        except FormulaError as exc:
            logger.warning("公式覆盖 %s.%s 计算失败：%s", tool, spec["output_key"], exc)
            continue
        updates[spec["output_key"]] = value
        ctx[spec["output_key"]] = value
    return updates


def version_for_tool(tool: str) -> str:
    ensure_defaults()
    base = FORMULA_VERSIONS.get(tool, tool)
    with new_session() as session:
        versions = [row.version for row in
                    session.query(FormulaDefinition)
                    .filter(FormulaDefinition.tool == tool,
                            FormulaDefinition.is_custom.is_(True)).all()]
    return f"{base}+ui{max(versions)}" if versions else base


def formula_constants() -> list[dict]:
    return [{"symbol": symbol, "label": label, "unit": unit,
             "value": CONSTANTS[symbol]}
            for symbol, (label, unit) in CONSTANT_META.items()]
