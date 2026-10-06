"""ORM 模型（对应 docs/03 数据模型；表结构约定见 docs/08 §2）。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # t-YYYYMMDD-NNN
    goal: Mapped[str] = mapped_column(Text)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 任务级模型选择（供应商 id）
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_step: Mapped[str | None] = mapped_column(String(8), nullable=True)
    corpus_version: Mapped[str] = mapped_column(String(32), default="corpus-v0.0.0")
    model_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    template_version: Mapped[str] = mapped_column(String(32), default="design-report-v1")
    cost_estimate_cny: Mapped[float] = mapped_column(Float, default=0.0)
    last_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class DesignParameter(Base):
    __tablename__ = "design_parameters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 参数 id（如 power.sa.area）
    mission_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(16))  # calc/doc/catalog/assumption/human
    source_ref: Mapped[str] = mapped_column(String(128))
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(8), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    parent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    derived_from: Mapped[list] = mapped_column(JSON, default=list)
    upstream_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CalculationRecord(Base):
    __tablename__ = "calculation_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # calc-YYYYMMDD-NNNN
    mission_id: Mapped[str] = mapped_column(String(32))
    tool: Mapped[str] = mapped_column(String(32))
    formula_version: Mapped[str] = mapped_column(String(32))
    inputs: Mapped[dict] = mapped_column(JSON)
    outputs: Mapped[dict] = mapped_column(JSON)
    units_map: Mapped[dict] = mapped_column(JSON, default=dict)
    code_commit: Mapped[str] = mapped_column(String(32), default="dev")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # vr-NNNN（任务内序号）
    mission_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(8))  # V1~V7
    status: Mapped[str] = mapped_column(String(8))  # pass/warn/block
    param_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Assumption(Base):
    __tablename__ = "assumptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # asm-NNNN（任务内序号）
    mission_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(Text)
    related_params: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open/confirmed/rejected
    registered_by: Mapped[str] = mapped_column(String(64), default="system")
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ReviewGate(Base):
    __tablename__ = "review_gates"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # g-NNN（任务内序号）
    mission_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # assumption_confirm / discrepancy_resolve / final_review
    param_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(8), nullable=True)  # accept/reject（待处理时为 None）
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    field: Mapped[str | None] = mapped_column(String(32), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    who: Mapped[str] = mapped_column(String(128))
    why: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(default=utcnow)


class CorpusManifest(Base):
    __tablename__ = "corpus_manifest"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    module: Mapped[str] = mapped_column(String(16))
    doc_type: Mapped[str] = mapped_column(String(16))
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON)  # 开发版：JSON 列表；目标：pgvector vector(1024)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
