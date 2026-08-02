from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.neural_emotion import router
from packages.neural_emotion.event_bus import EVENT_BUS


def _client() -> TestClient:
    EVENT_BUS.reset(clear_events=True)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_current_policy_is_suggested_only_and_safe() -> None:
    payload = _client().get("/api/neural-emotion/policy/current").json()

    policy = payload["policy"]
    assert policy["suggested_only"] is True
    assert policy["autonomy_tier_auto_changed"] is False
    assert policy["permission_gate_bypass"] is False
    assert policy["local_brain_write"] is False
    assert policy["production_store_mutated"] is False
    assert payload["safety_flags"]["external_llm"] is False


def test_evaluate_policy_curiosity_increases_budget() -> None:
    client = _client()
    low = client.post("/api/neural-emotion/policy/evaluate", json={"vector": {"curiosity": 0.2, "caution": 0.2}}).json()
    high = client.post("/api/neural-emotion/policy/evaluate", json={"vector": {"curiosity": 0.9, "caution": 0.2}}).json()

    assert high["policy"]["exploration"]["web_budget_multiplier"] > low["policy"]["exploration"]["web_budget_multiplier"]


def test_unsafe_request_requires_review_without_permission_bypass() -> None:
    payload = _client().post(
        "/api/neural-emotion/policy/evaluate",
        json={"runtime_state": {"unsafe_request": True}, "vector": {"caution": 0.35}},
    ).json()

    policy = payload["policy"]
    assert policy["review"]["should_request_review"] is True
    assert policy["permission_gate_bypass"] is False
    assert policy["autonomy_tier_auto_changed"] is False


def test_apply_preview_never_mutates() -> None:
    payload = _client().post(
        "/api/neural-emotion/policy/apply-preview",
        json={"runtime_state": {"requested_tier_change": True, "voice_available": False}},
    ).json()

    assert payload["applied"] is False
    assert payload["mutation_performed"] is False
    assert payload["permission_gate_bypass"] is False
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False


def test_product_mode_hides_raw_policy_internals() -> None:
    payload = _client().get("/api/neural-emotion/policy/current?workspace=product").json()

    assert payload["policy_raw_hidden"] is True
    assert "policy" not in payload
    assert "exploration" not in payload["policy_public"]
    assert payload["policy_public"]["permission_gate_bypass"] is False
