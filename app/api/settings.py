"""LLM 供应商设置接口（ADR-0006）：前端「设置」页使用。

- GET    /settings/llm        查看当前注册表（密钥掩码）
- PUT    /settings/llm        保存运行时注册表（api_key 省略 = 保留原值）
- DELETE /settings/llm        清除运行时覆盖（回落到环境变量 / 配置文件 / 内置默认）
- POST   /settings/llm/probe  探测端点连通性（OpenAI 兼容：拉取 /models 列表）
- POST   /settings/llm/test   对某个供应商做一次最小真实调用
"""
from __future__ import annotations

import time
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import api_error, require_token
from app.providers import current_mode, reset_provider
from app.providers.router import configured_status, models_summary
from app.providers.specs import (
    ProviderSpec,
    clear_runtime_specs,
    find_spec,
    load_specs,
    public_spec,
    save_runtime_specs,
)

router = APIRouter(tags=["Settings"])


class ProviderSpecIn(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    label: str = ""
    protocol: Literal["openai", "anthropic"] = "openai"
    base_url: str
    model: str
    api_key: str | None = None  # 省略 / null = 保留原值
    json_mode: bool = True
    enabled: bool = True
    keyless: bool = False
    timeout_s: float = 120.0
    price_in: float = 0.0
    price_out: float = 0.0


class SettingsPut(BaseModel):
    providers: list[ProviderSpecIn]


def _snapshot() -> dict:
    specs = load_specs()
    summary = models_summary()
    return {
        "mode": current_mode(),
        "primary": summary["primary"],
        "fallback_order": summary["fallback_order"],
        "configured": configured_status(),
        "providers": [public_spec(spec) for spec in specs],
    }


@router.get("/settings/llm")
def get_llm_settings(_: None = Depends(require_token)) -> dict:
    return _snapshot()


@router.put("/settings/llm")
def put_llm_settings(body: SettingsPut, _: None = Depends(require_token)) -> dict:
    if not body.providers:
        api_error(400, "SCHEMA_INVALID", "至少保留一个供应商条目", {"field": "providers"})

    existing = {spec.id: spec for spec in load_specs()}
    merged: list[ProviderSpec] = []
    for item in body.providers:
        if not item.base_url.strip() or not item.model.strip():
            api_error(400, "SCHEMA_INVALID",
                      f"供应商 {item.id} 缺少 base_url 或 model", {"field": item.id})
        api_key = item.api_key
        if api_key is None:  # 未改动 → 保留原值（含环境变量回填后的值）
            api_key = existing[item.id].api_key if item.id in existing else ""
        merged.append(ProviderSpec(
            id=item.id, label=item.label, protocol=item.protocol,
            base_url=item.base_url.strip(), model=item.model.strip(), api_key=api_key,
            api_key_env=(existing[item.id].api_key_env if item.id in existing
                         else f"{item.id.upper()}_API_KEY"),
            json_mode=item.json_mode, enabled=item.enabled, keyless=item.keyless,
            timeout_s=item.timeout_s, price_in=item.price_in, price_out=item.price_out,
        ))

    save_runtime_specs(merged)
    reset_provider()
    return _snapshot()


@router.delete("/settings/llm")
def reset_llm_settings(_: None = Depends(require_token)) -> dict:
    """清除运行时覆盖，恢复为 环境变量 / config/llm.json / 内置默认。"""
    clear_runtime_specs()
    reset_provider()
    return _snapshot()


class ProbeBody(BaseModel):
    protocol: Literal["openai", "anthropic"] = "openai"
    base_url: str
    api_key: str | None = None
    model: str | None = None
    id: str | None = None


@router.post("/settings/llm/probe")
def probe_provider(body: ProbeBody, _: None = Depends(require_token)) -> dict:
    api_key = body.api_key
    if api_key is None:  # 未提供 → 用注册表里同 id 或同 base_url 的密钥
        for spec in load_specs():
            if (body.id and spec.id == body.id) or \
               (not body.id and spec.base_url.rstrip("/") == body.base_url.rstrip("/")):
                api_key = spec.api_key
                break
    api_key = api_key or ""
    base_url = body.base_url.rstrip("/")
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=20.0) as client:
            if body.protocol == "anthropic":
                if not body.model:
                    return {"ok": False, "error": "anthropic 协议探测需要 model"}
                response = client.post(
                    f"{base_url}/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    json={"model": body.model, "max_tokens": 8,
                          "messages": [{"role": "user", "content": "ping"}]},
                )
                if response.status_code >= 400:
                    return {"ok": False, "status": response.status_code, "error": response.text[:300]}
                return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000)}

            response = client.get(f"{base_url}/models",
                                  headers={"Authorization": f"Bearer {api_key}"})
            if response.status_code >= 400:
                return {"ok": False, "status": response.status_code, "error": response.text[:300]}
            data = response.json()
            models = sorted({str(item.get("id")) for item in (data.get("data") or [])
                             if isinstance(item, dict) and item.get("id")})
            return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000),
                    "models": models}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)[:300]}


class TestBody(BaseModel):
    id: str


@router.post("/settings/llm/test")
def test_provider(body: TestBody, _: None = Depends(require_token)) -> dict:
    """对注册表中某个供应商做一次最小真实调用（确认鉴权与模型名可用）。"""
    spec = find_spec(body.id)
    if spec is None:
        api_error(404, "SCHEMA_INVALID", f"供应商不存在：{body.id}", {"field": "id"})
    if not (spec.api_key or spec.keyless):
        return {"ok": False, "error": "该供应商未配置 API Key"}

    started = time.perf_counter()
    try:
        if spec.protocol == "anthropic":
            from app.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider(name=spec.id, model=spec.model, api_key=spec.api_key,
                                         base_url=spec.base_url, timeout_s=spec.timeout_s)
        else:
            from app.providers.openai_compat import OpenAICompatProvider

            provider = OpenAICompatProvider(name=spec.id, model=spec.model, base_url=spec.base_url,
                                            api_key=spec.api_key or "none",
                                            timeout_s=spec.timeout_s, json_mode=False)
        result = provider.call("你是连通性测试助手。", "只回复 OK", 0.0)
    except Exception as exc:  # noqa: BLE001 —— 探测类接口统一返回 ok=false
        return {"ok": False, "error": str(exc)[:300]}

    return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": spec.model, "echo": (result.text or "").strip()[:40]}
