"""OpenAI 兼容供应商（DeepSeek / Qwen / OpenAI / Ollama 通用）。"""
from __future__ import annotations

import httpx

from app.providers.base import ProviderCallResult, ProviderError


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 60.0,
        json_mode: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._json_mode = json_mode
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def call(self, system: str, user: str, temperature: float) -> ProviderCallResult:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} 网络错误：{exc}", provider=self.name) from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} HTTP {response.status_code}: {response.text[:200]}",
                provider=self.name, status=response.status_code,
            )

        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} 响应结构异常", provider=self.name) from exc

        usage = data.get("usage") or {}
        return ProviderCallResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
        )
