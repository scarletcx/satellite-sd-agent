"""OpenAI 兼容供应商（DeepSeek / Qwen / OpenAI / Ollama 通用）。"""
from __future__ import annotations

import json

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

    def _body(self, system: str, user: str, temperature: float,
              options: dict | None, stream: bool) -> dict:
        options = options or {}
        body: dict = {
            "model": options.get("model") or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if stream:
            body["stream"] = True
        if self._json_mode and options.get("json_mode", True) and not stream:
            body["response_format"] = {"type": "json_object"}
        if options.get("reasoning_effort"):
            body["reasoning_effort"] = options["reasoning_effort"]
        return body

    def call(self, system: str, user: str, temperature: float,
             options: dict | None = None) -> ProviderCallResult:
        body = self._body(system, user, temperature, options, stream=False)
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

    def call_stream(self, system: str, user: str, temperature: float,
                    options: dict | None = None):
        """SSE 流式输出（仅文本增量）。"""
        body = self._body(system, user, temperature, options, stream=True)
        try:
            with self._client.stream("POST", "/chat/completions", json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    raise ProviderError(
                        f"{self.name} HTTP {response.status_code}: {response.text[:200]}",
                        provider=self.name, status=response.status_code,
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} 网络错误：{exc}", provider=self.name) from exc
