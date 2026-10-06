"""供应商链构建（ADR-0002 / ADR-0006）。

- 供应商集合与顺序来自注册表（specs.py）：运行时设置 > 环境变量 > config/llm.json > 内置默认；
- 环境变量 LLM_ORDER 可按 id 过滤/重排链；
- 未配置密钥（且非 keyless）的供应商自动跳过。
"""
from __future__ import annotations

import os

from app.providers.anthropic import AnthropicProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.specs import ProviderSpec, find_spec, load_specs


def active_specs() -> list[ProviderSpec]:
    specs = [spec for spec in load_specs() if spec.enabled and spec.base_url and spec.model]
    order_env = os.getenv("LLM_ORDER", "").strip()
    if order_env:
        ranked = {name.strip(): index for index, name in enumerate(order_env.split(",")) if name.strip()}
        specs = [spec for spec in specs if spec.id in ranked]
        specs.sort(key=lambda spec: ranked[spec.id])
    return specs


def configured_ids() -> list[str]:
    return [spec.id for spec in active_specs() if spec.api_key or spec.keyless]


def configured_status() -> dict:
    return {
        spec.id: ("configured" if (spec.enabled and (spec.api_key or spec.keyless) and spec.base_url)
                  else "not_configured")
        for spec in load_specs()
    }


def models_summary() -> dict:
    configured = configured_ids()
    return {
        "primary": configured[0] if configured else "stub",
        "fallback_order": [spec.id for spec in active_specs()],
        "models": {spec.id: spec.model for spec in load_specs()},
    }


def cost_cny(provider_id: str, tokens_in: int, tokens_out: int) -> float:
    spec = find_spec(provider_id)
    price_in = spec.price_in if spec else 0.0
    price_out = spec.price_out if spec else 0.0
    return round(tokens_in / 1000 * price_in + tokens_out / 1000 * price_out, 6)


def build_raw_providers(transport=None) -> list:
    """按链顺序实例化可用供应商（未配置密钥的跳过）。"""
    providers: list = []
    for spec in active_specs():
        if not (spec.api_key or spec.keyless):
            continue
        if spec.protocol == "anthropic":
            providers.append(AnthropicProvider(
                name=spec.id, model=spec.model, api_key=spec.api_key,
                base_url=spec.base_url, timeout_s=spec.timeout_s, transport=transport,
            ))
        else:
            providers.append(OpenAICompatProvider(
                name=spec.id, model=spec.model, base_url=spec.base_url,
                api_key=spec.api_key or "none", timeout_s=spec.timeout_s,
                json_mode=spec.json_mode, transport=transport,
            ))
    return providers
