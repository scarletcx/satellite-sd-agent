"""公式库测试：列表/试算/编辑/重置、非法表达式拦截、S5 使用自定义公式。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create(client) -> str:
    return client.post("/api/v1/missions", headers=HEADERS, json={
        "goal": "设计一颗 500km SSO 光学遥感小卫星",
        "constraints": {"orbit_type": "SSO", "altitude_km": 500, "mass_limit_kg": 80},
    }).json()["task_id"]


def _wait(client, task_id: str, statuses=("awaiting_gate", "succeeded", "failed"),
          timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    detail: dict = {}
    while time.time() < deadline:
        detail = client.get(f"/api/v1/missions/{task_id}", headers=HEADERS).json()
        if detail["status"] in statuses:
            return detail
        time.sleep(0.05)
    return detail


def test_formula_list_preview_and_constants(client):
    listing = client.get("/api/v1/formulas", headers=HEADERS)
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) >= 20
    assert any(item["id"] == "orbit.period_min" for item in items)

    detail = client.get("/api/v1/formulas/orbit.period_min", headers=HEADERS).json()
    assert detail["expression"] and detail["variables"]
    assert detail["history"]

    preview = client.post("/api/v1/formulas/orbit.period_min/preview",
                          headers=HEADERS, json={})
    assert preview.status_code == 200, preview.text
    assert 94 < preview.json()["value"] < 95

    constants = client.get("/api/v1/formulas/constants", headers=HEADERS).json()["items"]
    assert any(item["symbol"] == "RE_KM" for item in constants)


def test_formula_update_validation_and_reset(client):
    original = client.get("/api/v1/formulas/orbit.period_min", headers=HEADERS).json()
    updated = client.put("/api/v1/formulas/orbit.period_min", headers=HEADERS, json={
        "expression": "2*pi*sqrt((RE_KM+alt_km)**3/MU_EARTH_KM3_S2)/60*1.1",
        "description": "测试覆盖：周期放大 10%",
        "updated_by": "tester",
    })
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["is_custom"] is True
    assert payload["version"] == original["version"] + 1

    preview = client.post("/api/v1/formulas/orbit.period_min/preview",
                          headers=HEADERS, json={}).json()
    assert 104 < preview["value"] < 105

    bad = client.put("/api/v1/formulas/orbit.period_min", headers=HEADERS, json={
        "expression": "__import__('os').system('echo hacked')",
    })
    assert bad.status_code == 400, bad.text

    reset = client.post("/api/v1/formulas/orbit.period_min/reset",
                        headers=HEADERS, json={"updated_by": "tester"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["is_custom"] is False
    assert reset.json()["expression"] == original["default_expression"]


def test_custom_formula_is_used_by_s5(client):
    original = client.get("/api/v1/formulas/mass.total_with_margin", headers=HEADERS).json()
    try:
        changed = client.put("/api/v1/formulas/mass.total_with_margin", headers=HEADERS, json={
            "expression": "(dry_mass_kg + propellant_kg) * (1 + margin_pct) * 1.01",
            "description": "测试覆盖：总重 +1%",
            "updated_by": "tester",
        })
        assert changed.status_code == 200, changed.text

        task_id = _create(client)
        gate = _wait(client, task_id)
        assert gate["status"] == "awaiting_gate", gate

        accepted = client.post(f"/api/v1/missions/{task_id}/reviews/accept-all",
                               headers=HEADERS, json={"reviewer": "tester"})
        assert accepted.status_code == 200, accepted.text
        detail = _wait(client, task_id, ("succeeded", "failed"), timeout_s=15)
        assert detail["status"] == "succeeded", detail

        params = {item["id"]: item for item in
                  client.get(f"/api/v1/missions/{task_id}/parameters",
                             headers=HEADERS).json()["items"]}
        dry = params["mass.dry"]["value"]
        propellant = params["mass.propellant"]["value"]
        margin = params["mass.margin_pct"]["value"] / 100.0
        expected = (dry + propellant) * (1 + margin) * 1.01
        assert params["mass.total_with_margin"]["value"] == pytest.approx(expected, rel=1e-6)
    finally:
        client.put("/api/v1/formulas/mass.total_with_margin", headers=HEADERS, json={
            "expression": original["default_expression"],
            "description": original["description"],
            "updated_by": "tester",
        })
