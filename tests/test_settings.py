"""供应商注册表与设置接口测试（ADR-0006）。"""
import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.providers.specs import (
    ProviderSpec,
    clear_runtime_specs,
    find_spec,
    load_specs,
    public_spec,
    save_runtime_specs,
)

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def _clean_runtime():
    init_db()
    clear_runtime_specs()
    yield
    clear_runtime_specs()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_builtin_defaults_loaded():
    ids = [spec.id for spec in load_specs()]
    assert ids[:5] == ["deepseek", "qwen", "openai", "claude", "ollama"]


def test_env_override_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    assert find_spec("deepseek").model == "deepseek-reasoner"


def test_runtime_override_replaces_registry():
    save_runtime_specs([ProviderSpec(
        id="aiapi", label="第三方网关", protocol="openai",
        base_url="https://aiapi.example/v1", model="gpt-4o-mini",
        api_key="sk-test-123456", json_mode=False, price_in=0.01,
    )])
    specs = load_specs()
    assert [spec.id for spec in specs] == ["aiapi"]
    assert specs[0].json_mode is False
    assert specs[0].model == "gpt-4o-mini"


def test_public_spec_masks_key():
    public = public_spec(ProviderSpec(id="x", api_key="sk-abcdefghijklmnop"))
    assert "api_key" not in public
    assert public["has_key"] is True
    assert "…" in public["key_masked"]


def test_settings_roundtrip_keeps_key_when_omitted(client):
    response = client.get("/api/v1/settings/llm", headers=HEADERS)
    assert response.status_code == 200
    assert len(response.json()["providers"]) == 5
    assert all("api_key" not in item for item in response.json()["providers"])

    payload = {"providers": [{
        "id": "aiapi", "label": "第三方网关", "protocol": "openai",
        "base_url": "https://aiapi.example/v1", "model": "gpt-4o-mini",
        "api_key": "sk-test-secret", "json_mode": False,
    }]}
    saved = client.put("/api/v1/settings/llm", headers=HEADERS, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["providers"][0]["has_key"] is True
    assert find_spec("aiapi").api_key == "sk-test-secret"

    payload["providers"][0].pop("api_key")  # 省略 = 保留原值
    client.put("/api/v1/settings/llm", headers=HEADERS, json=payload)
    assert find_spec("aiapi").api_key == "sk-test-secret"

    restored = client.delete("/api/v1/settings/llm", headers=HEADERS)
    assert restored.status_code == 200
    assert len(restored.json()["providers"]) == 5


def test_settings_put_rejects_missing_model(client):
    response = client.put("/api/v1/settings/llm", headers=HEADERS, json={
        "providers": [{"id": "bad", "base_url": "https://x/v1", "model": ""}]
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SCHEMA_INVALID"


def test_order_providers_prefers_selected():
    from app.providers import _order_providers

    class FakeProvider:
        def __init__(self, name: str):
            self.name = name

    providers = [FakeProvider("a"), FakeProvider("b"), FakeProvider("c")]
    assert [p.name for p in _order_providers(providers, "c")] == ["c", "a", "b"]
    assert [p.name for p in _order_providers(providers, None)] == ["a", "b", "c"]
    # 未命中 → 保持原顺序（其余仍可兜底）
    assert [p.name for p in _order_providers(providers, "x")] == ["a", "b", "c"]
