"""LLM 适配层测试：用量解析 / 修复重试 / 供应商降级 / 全失败 / 提示词渲染 / 桩模式。"""
import json

import httpx
import pytest

from app.config import settings
from app.providers import chat_json, resolve_mode
from app.providers.base import ProviderError
from app.providers.chain import ProviderChain
from app.providers.openai_compat import OpenAICompatProvider

PROMPT_DIR = settings.prompts_dir


def _provider(name: str, handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name=name, model=f"{name}-model", base_url="https://mock.local/v1",
        api_key="test", transport=httpx.MockTransport(handler),
    )


def _ok(content: str, tokens=(11, 7)):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
        })
    return handler


def _http_error(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})
    return handler


def test_openai_compat_parses_payload_and_usage():
    provider = _provider("deepseek", _ok(json.dumps({"goal": "g1"})))
    result = provider.call("sys", "user", 0.2)
    assert json.loads(result.text)["goal"] == "g1"
    assert result.tokens_in == 11
    assert result.tokens_out == 7


def test_chain_repairs_invalid_json_then_succeeds():
    responses = iter([
        httpx.Response(200, json={"choices": [{"message": {"content": "这不是 JSON"}}], "usage": {}}),
        httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({"goal": "修复成功"})}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }),
    ])
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return next(responses)

    chain = ProviderChain([_provider("deepseek", handler)], prompt_dir=PROMPT_DIR)
    payload, usage = chain.chat_json("S1", {"goal": "g", "constraints": {}})
    assert payload["goal"] == "修复成功"
    assert calls["n"] == 2
    assert usage["repair_attempts"] == 1
    assert usage["provider"] == "deepseek"


def test_chain_falls_back_to_next_provider():
    bad = _provider("deepseek", _http_error(429))
    good = _provider("qwen", _ok(json.dumps({"goal": "g2"})))
    chain = ProviderChain([bad, good], prompt_dir=PROMPT_DIR)
    payload, usage = chain.chat_json("S1", {"goal": "g", "constraints": {}})
    assert payload["goal"] == "g2"
    assert usage["provider"] == "qwen"
    assert usage["repair_attempts"] == 0


def test_chain_all_failed_raises_provider_error():
    chain = ProviderChain([_provider("openai", _http_error(500))], prompt_dir=PROMPT_DIR)
    with pytest.raises(ProviderError):
        chain.chat_json("S1", {"goal": "g", "constraints": {}})


def test_empty_provider_list_raises():
    with pytest.raises(ProviderError):
        ProviderChain([], prompt_dir=PROMPT_DIR)


def test_prompt_render_replaces_variables():
    chain = ProviderChain([_provider("mock", _ok("{}"))], prompt_dir=PROMPT_DIR)
    rendered = chain._render(chain._load_prompt("S1"),
                             {"goal": "G-测试", "constraints": {"altitude_km": 500}})
    assert "G-测试" in rendered
    assert "500" in rendered
    assert "<<GOAL>>" not in rendered
    assert "<<CONSTRAINTS_JSON>>" not in rendered


def test_stub_mode_via_facade():
    assert resolve_mode() == "stub"
    payload = chat_json("S1", {"goal": "设计一颗 500km SSO 卫星", "constraints": {}})
    assert payload["goal"] == "设计一颗 500km SSO 卫星"
