"""步骤公共工具：参数 upsert / 读取，设计输入分组读取与待确认统计。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assumption, DesignParameter

INPUT_GROUPS: tuple[str, ...] = ("orbit", "mass", "power", "eps", "data", "link")
BLOCKING_PARAM_STATUSES: tuple[str, ...] = ("draft", "needs_review", "rejected")


class InputNotConfirmedError(RuntimeError):
    """存在未确认（或已驳回）的设计输入草案，不允许进入计算。"""


def load_inputs(session: Session, mission_id: str, *, require_confirmed: bool = True) -> dict:
    """读取 S4 落库的分组设计输入（id = input.<group>，payload = 计算输入对象）。"""
    rows = session.scalars(
        select(DesignParameter).where(
            DesignParameter.mission_id == mission_id,
            DesignParameter.id.like("input.%"),
        )
    ).all()
    blocking = [row.id for row in rows if row.status in ("draft", "rejected")]
    if require_confirmed and blocking:
        raise InputNotConfirmedError(f"设计输入未确认或已驳回：{blocking}（请先完成输入门禁评审）")
    return {row.id.split(".", 1)[1]: dict(row.payload or {}) for row in rows}


def untraceable_numbers(texts: list[str], allowed: list[float]) -> list[float]:
    """LLM 文本输出的数字白名单校验：返回无法对应到 IR / 约束 / 任务书的数字。

    章节号（1~12）与年份（2000~2100）不算违规；标识符（S1、calc-xxx）先行剥离。
    """
    from app.tools.doc.check import IDENTIFIER_RE, NUMBER_RE

    allowed_values = list(allowed)
    violations: list[float] = []
    for text in texts:
        cleaned = IDENTIFIER_RE.sub(" ", text or "")
        for match in NUMBER_RE.finditer(cleaned):
            value = float(match.group(0))
            if 2000 <= value <= 2100:
                continue  # 年份
            if value.is_integer() and 1 <= value <= 12 and match.start() == 0:
                continue  # 行首的章节编号（如「12 引用与假设」）
            if not any(abs(value - item) <= max(0.05, abs(item) * 0.001) for item in allowed_values):
                violations.append(value)
    return violations


def unconfirmed_total(session: Session, mission_id: str) -> int:
    """待人工处理的确认项数量：未确认/被驳回的参数 + 未确认的假设。"""
    params = session.scalar(
        select(func.count()).select_from(DesignParameter).where(
            DesignParameter.mission_id == mission_id,
            DesignParameter.status.in_(BLOCKING_PARAM_STATUSES),
        )
    ) or 0
    assumptions = session.scalar(
        select(func.count()).select_from(Assumption).where(
            Assumption.mission_id == mission_id,
            Assumption.status == "open",
        )
    ) or 0
    return params + assumptions


def upsert_parameter(
    session: Session,
    mission_id: str,
    *,
    id: str,
    name: str,
    value: float,
    unit: str,
    source_type: str,
    source_ref: str,
    margin: float | None = None,
    parent: str | None = None,
    confidence: str = "high",
    status: str = "proposed",
    derived_from: list | None = None,
) -> DesignParameter:
    row = session.get(DesignParameter, (id, mission_id))
    if row is None:
        row = DesignParameter(
            id=id, mission_id=mission_id, name=name, value=value, unit=unit,
            source_type=source_type, source_ref=source_ref, margin=margin,
            parent=parent, confidence=confidence, status=status,
            derived_from=derived_from or [],
        )
        session.add(row)
    else:
        row.value = value
        row.source_type = source_type
        row.source_ref = source_ref
        row.margin = margin
        row.confidence = confidence
        row.version += 1
    return row


def load_params(session: Session, mission_id: str) -> list[dict]:
    rows = session.scalars(
        select(DesignParameter)
        .where(DesignParameter.mission_id == mission_id)
        .order_by(DesignParameter.id)
    ).all()
    return [
        {
            "id": r.id, "name": r.name, "value": r.value, "unit": r.unit,
            "source_type": r.source_type, "source_ref": r.source_ref,
            "status": r.status, "confidence": r.confidence, "margin": r.margin,
            "version": r.version, "parent": r.parent, "derived_from": list(r.derived_from or []),
        }
        for r in rows
    ]
