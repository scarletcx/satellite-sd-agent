"""LLM 供应商注册表（ADR-0006）：支持任意数量的第三方（OpenAI 兼容 / Anthropic 协议）。

配置优先级：**运行时设置（DB，前端可改） > 环境变量 > config/llm.json > 内置默认**。
密钥存储：运行时密钥以明文存于本地 SQLite（演示级；生产环境应替换为密钥管理服务）。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass

from app.config import BASE_DIR
from app.db import new_session
from app.models import AppMeta

CONFIG_PATH = BASE_DIR / "config" / "llm.json"
SETTINGS_KEY = "llm.providers"

# 兼容旧环境变量名（docs/12 §3）
_LEGACY_BASE_ENV = {"qwen": "DASHSCOPE_BASE_URL"}
_LEGACY_KEY_ENV = {"qwen": "DASHSCOPE_API_KEY"}


@dataclass
class ProviderSpec:
    id: str
    label: str = ""
    protocol: str = "openai"          # openai | anthropic
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    api_key_env: str = ""
    json_mode: bool = True
    enabled: bool = True
    keyless: bool = False             # 本地服务（如 Ollama）无需 Key
    timeout_s: float = 120.0
    price_in: float = 0.0             # 元 / 1K tokens（仅用于成本估算）
    price_out: float = 0.0


def _builtin_defaults() -> list[ProviderSpec]:
    return [
        ProviderSpec(id="deepseek", label="DeepSeek 官方", protocol="openai",
                     base_url="https://api.deepseek.com/v1", model="deepseek-chat",
                     api_key_env="DEEPSEEK_API_KEY", json_mode=True,
                     price_in=0.002, price_out=0.008),
        ProviderSpec(id="qwen", label="通义千问（DashScope 兼容模式）", protocol="openai",
                     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen-plus",
                     api_key_env="DASHSCOPE_API_KEY", json_mode=True,
                     price_in=0.004, price_out=0.012),
        ProviderSpec(id="openai", label="OpenAI", protocol="openai",
                     base_url="https://api.openai.com/v1", model="gpt-4o-mini",
                     api_key_env="OPENAI_API_KEY", json_mode=True,
                     price_in=0.010, price_out=0.030),
        ProviderSpec(id="claude", label="Anthropic Claude", protocol="anthropic",
                     base_url="https://api.anthropic.com", model="claude-sonnet-4-5",
                     api_key_env="ANTHROPIC_API_KEY", json_mode=False,
                     price_in=0.022, price_out=0.110),
        ProviderSpec(id="ollama", label="本地 Ollama", protocol="openai",
                     base_url="http://localhost:11434/v1", model="qwen2.5:14b",
                     keyless=True, json_mode=False),
    ]


def _spec_from_dict(data: dict) -> ProviderSpec:
    fields = {field.name for field in dataclasses.fields(ProviderSpec)}
    payload = {key: value for key, value in data.items() if key in fields}
    payload.setdefault("id", "")
    if payload.get("protocol") not in ("openai", "anthropic"):
        payload["protocol"] = "openai"
    return ProviderSpec(**payload)


def _from_file() -> list[ProviderSpec] | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list) or not providers:
        return None
    return [_spec_from_dict(item) for item in providers if isinstance(item, dict) and item.get("id")]


def _apply_env(specs: list[ProviderSpec]) -> list[ProviderSpec]:
    timeout = float(os.getenv("LLM_TIMEOUT_S", "120"))
    result = []
    for spec in specs:
        prefix = spec.id.upper()
        base_url = os.getenv(f"{prefix}_BASE_URL", "").strip()
        if not base_url and spec.id in _LEGACY_BASE_ENV:
            base_url = os.getenv(_LEGACY_BASE_ENV[spec.id], "").strip()
        model = os.getenv(f"{prefix}_MODEL", "").strip()
        key = ""
        if spec.api_key_env:
            key = os.getenv(spec.api_key_env, "").strip()
        if not key and spec.id in _LEGACY_KEY_ENV:
            key = os.getenv(_LEGACY_KEY_ENV[spec.id], "").strip()
        if spec.id == "ollama":
            host = os.getenv("OLLAMA_HOST", "").strip()
            if host:
                base_url = host.rstrip("/") + "/v1"
        result.append(dataclasses.replace(
            spec,
            base_url=base_url or spec.base_url,
            model=model or spec.model,
            api_key=key or spec.api_key,
            timeout_s=timeout,
            price_in=float(os.getenv(f"PRICE_{prefix}_IN", spec.price_in)),
            price_out=float(os.getenv(f"PRICE_{prefix}_OUT", spec.price_out)),
        ))
    return result


def _load_runtime() -> list[ProviderSpec] | None:
    with new_session() as session:
        row = session.get(AppMeta, SETTINGS_KEY)
    if row is None or not row.value:
        return None
    try:
        items = json.loads(row.value)
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list):
        return None
    return [_spec_from_dict(item) for item in items if isinstance(item, dict) and item.get("id")]


def _apply_runtime(specs: list[ProviderSpec]) -> list[ProviderSpec]:
    runtime = _load_runtime()
    if runtime is None:
        return specs
    # 运行时列表即最终列表（含顺序）；密钥为空时用环境变量回填（保持纯环境变量部署仍可用）
    result = []
    for spec in runtime:
        key = spec.api_key
        if not key:
            env_name = spec.api_key_env or _LEGACY_KEY_ENV.get(spec.id, "")
            if not env_name:
                env_name = f"{spec.id.upper()}_API_KEY"
            key = os.getenv(env_name, "").strip()
        result.append(dataclasses.replace(spec, api_key=key))
    return result


def load_specs() -> list[ProviderSpec]:
    specs = _from_file() or _builtin_defaults()
    return _apply_runtime(_apply_env(specs))


def save_runtime_specs(specs: list[ProviderSpec]) -> None:
    payload = json.dumps([dataclasses.asdict(spec) for spec in specs], ensure_ascii=False)
    with new_session() as session:
        session.merge(AppMeta(key=SETTINGS_KEY, value=payload))
        session.commit()


def clear_runtime_specs() -> None:
    with new_session() as session:
        row = session.get(AppMeta, SETTINGS_KEY)
        if row is not None:
            session.delete(row)
            session.commit()


def find_spec(spec_id: str) -> ProviderSpec | None:
    return next((spec for spec in load_specs() if spec.id == spec_id), None)


def public_spec(spec: ProviderSpec) -> dict:
    """对外（前端）表示：密钥掩码化。"""
    data = dataclasses.asdict(spec)
    key = data.pop("api_key", "")
    data["has_key"] = bool(key)
    data["key_masked"] = mask_key(key)
    return data


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return "*" * len(key)
    return f"{key[:6]}…{key[-4:]}"
