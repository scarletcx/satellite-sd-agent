"""LLM 适配层入口（ADR-0002 / ADR-0006）。

- 桩模式：STUB_LLM=1，或（未显式设置时）注册表中没有任何可用供应商；
- 真实模式：多供应商降级链 + 提示词文件 + 结构化输出修复重试；
- 用量（provider/model/tokens/成本）自动写入 trace，并累计到任务的 cost_estimate_cny。
"""
from __future__ import annotations

import os

from app.providers.stub import StubProvider

_stub = StubProvider()
_chains: dict[str, object] = {}


def _order_providers(providers: list, preferred: str | None) -> list:
    """任务级模型选择：优先供应商排到链首，其余保持注册表顺序（稳定排序）。"""
    if not preferred:
        return providers
    return sorted(providers, key=lambda provider: 0 if provider.name == preferred else 1)


def _mission_provider(task_id: str | None) -> str | None:
    if not task_id:
        return None
    try:
        from app.db import new_session
        from app.models import Mission

        with new_session() as session:
            mission = session.get(Mission, task_id)
            return mission.provider_id if mission is not None else None
    except Exception:  # noqa: BLE001 —— 数据库不可用时退回默认链
        return None


def resolve_mode() -> str:
    explicit = os.getenv("STUB_LLM", "").strip()
    if explicit == "1":
        return "stub"
    if explicit == "0":
        return "real"
    from app.providers.router import configured_ids

    return "real" if configured_ids() else "stub"


def get_provider(preferred: str | None = None):
    if resolve_mode() == "stub":
        return _stub
    key = preferred or ""
    if key not in _chains:
        from app.config import settings
        from app.providers.chain import ProviderChain
        from app.providers.router import build_raw_providers

        _chains[key] = ProviderChain(
            _order_providers(build_raw_providers(), preferred),
            prompt_dir=settings.prompts_dir,
        )
    return _chains[key]


def reset_provider() -> None:
    """配置变更或测试注入后重建链。"""
    _chains.clear()


def chat_json(step: str, context: dict) -> dict:
    """步骤层统一入口：按任务选择供应商（优先），返回结构化 payload 并记录用量。"""
    preferred = _mission_provider(context.get("task_id"))
    payload, usage = get_provider(preferred).chat_json(step, context)
    _record_usage(context.get("task_id"), step, usage)
    return payload


def _record_usage(task_id: str | None, step: str, usage: dict) -> None:
    if not task_id:
        return
    from app.db import new_session
    from app.models import Mission
    from app.tracing import trace

    trace(task_id, {
        "step": step,
        "type": "llm_call",
        "provider": usage.get("provider"),
        "model": usage.get("model"),
        "tokens": {"in": usage.get("tokens_in"), "out": usage.get("tokens_out")},
        "cost_estimate_cny": usage.get("cost_cny"),
        "repair_attempts": usage.get("repair_attempts", 0),
    })

    cost = float(usage.get("cost_cny") or 0.0)
    if cost:
        with new_session() as session:
            mission = session.get(Mission, task_id)
            if mission is not None:
                mission.cost_estimate_cny = round((mission.cost_estimate_cny or 0.0) + cost, 4)
                session.commit()


def provider_status() -> dict:
    from app.providers.router import configured_status

    return configured_status()


def models_summary() -> dict:
    from app.providers.router import models_summary as summary

    return summary()


def current_mode() -> str:
    return resolve_mode()
