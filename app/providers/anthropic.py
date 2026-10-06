"""Anthropic Claude 供应商（Messages API）。"""
from __future__ import annotations

import httpx

from app.providers.base import ProviderCallResult, ProviderError

API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = 60.0,
        max_tokens: int = 4096,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._max_tokens = max_tokens
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            headers={"x-api-key": api_key, "anthropic-version": API_VERSION},
        )

    def call(self, system: str, user: str, temperature: float) -> ProviderCallResult:
        body = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            response = self._client.post("/v1/messages", json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} 网络错误：{exc}", provider=self.name) from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} HTTP {response.status_code}: {response.text[:200]}",
                provider=self.name, status=response.status_code,
            )

        data = response.json()
        try:
            text = "".join(block.get("text", "") for block in data["content"])
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"{self.name} 响应结构异常", provider=self.name) from exc

        usage = data.get("usage") or {}
        return ProviderCallResult(
            text=text,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
        )
