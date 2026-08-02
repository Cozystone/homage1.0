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


def test_status_reports_proof_only_safety_flags() -> None:
    payload = _client().get("/api/neural-emotion/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert payload["safety_flags"]["external_llm"] is False
    assert payload["safety_flags"]["real_emotion_claim"] is False
    assert payload["safety_flags"]["local_brain_write"] is False


def test_event_updates_vector_without_mutation_permissions() -> None:
    payload = _client().post("/api/neural-emotion/event", json={"event_type": "unsafe_request", "intensity": 1.0}).json()

    assert payload["updated"] is True
    assert payload["snapshot"]["vector"]["caution"] >= 0.0
    assert payload["snapshot"]["agentic_controls"]["permission_gate_bypass"] is False
    assert payload["safety_flags"]["production_store_mutated"] is False


def test_text_event_infers_locally() -> None:
    payload = _client().post("/api/neural-emotion/event", json={"text": "안녕, 새 아이디어가 있어"}).json()

    assert payload["updated"] is True
    assert payload["inferred_event"] == "from_text"
    assert payload["safety_flags"]["external_sllm"] is False


def test_controls_endpoint_returns_all_bridges() -> None:
    payload = _client().post("/api/neural-emotion/controls", json={"risk": 0.7, "selected_engine": "fish2", "audio_available": False}).json()

    controls = payload["controls"]
    assert "surface_bias" in controls
    assert "voice_controls" in controls
    assert "splatra_controls" in controls
    assert "agentic_controls" in controls
    assert controls["agentic_controls"]["permission_gate_bypass"] is False


def test_runtime_event_emit_records_bounded_event() -> None:
    payload = _client().post(
        "/api/neural-emotion/events/emit",
        json={"source": "web_explorer", "event_type": "novelty_found", "payload_summary": "new source"},
    ).json()

    assert payload["result"]["accepted"] is True
    assert payload["events"][-1]["event_type"] == "novelty_found"
    assert payload["snapshot"]["vector"]["curiosity"] > 0.45


def test_runtime_event_rejects_private_payload() -> None:
    payload = _client().post(
        "/api/neural-emotion/events/emit",
        json={
            "source": "user_action",
            "event_type": "memory_request",
            "payload": {"secret": "do not store"},
            "private_payload": True,
        },
    ).json()

    assert payload["result"]["accepted"] is False
    assert payload["result"]["denied_reason"] == "private_payload_not_stored"
    assert payload["events"] == []


def test_reset_is_lab_dev_only() -> None:
    client = _client()

    product = client.post("/api/neural-emotion/reset", json={"workspace": "product"}).json()
    lab = client.post("/api/neural-emotion/reset", json={"workspace": "lab"}).json()

    assert product["allowed"] is False
    assert lab["allowed"] is True
