from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.routers.agentic_micro_os import router as agentic_router
from app.routers.neural_emotion import router as neural_router
from packages.neural_emotion.event_bus import EVENT_BUS


def _client() -> TestClient:
    EVENT_BUS.reset(clear_events=True)
    app = FastAPI()
    app.include_router(neural_router)
    app.include_router(agentic_router)
    return TestClient(app)


def test_permission_tier4_wiring_updates_event_log() -> None:
    client = _client()

    client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={
            "enabled_by": "tester",
            "typed_phrase": "ENABLE FULL HOST AUTHORITY",
            "duration_sec": 60,
            "sub_switches": {},
        },
    )
    payload = client.get("/api/neural-emotion/events").json()

    assert any(event["event_type"] in {"tier4_enabled", "host_action_denied"} for event in payload["events"])
    assert payload["safety_flags"]["local_brain_write"] is False


def test_splatra_generation_wiring_updates_event_log() -> None:
    client = _client()

    client.post(
        "/api/agentic-os/splatra/imagination/generate",
        json={"archetype": "orb", "particle_budget": 64, "include_particles": False},
    )
    payload = client.get("/api/neural-emotion/events").json()

    assert any(event["source"] == "splatra_imagination" and event["event_type"] == "splatra_generation_success" for event in payload["events"])
    assert payload["safety_flags"]["production_store_mutated"] is False


def test_host_executor_denied_action_updates_event_log_without_execution() -> None:
    client = _client()

    client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "shell", "operator_id": "tester"},
    )
    payload = client.get("/api/neural-emotion/events").json()

    assert any(event["source"] == "host_executor" and event["event_type"] == "host_action_denied" for event in payload["events"])
    assert payload["snapshot"]["agentic_controls"]["permission_gate_bypass"] is False


def test_product_surface_does_not_mount_raw_emotion_panel() -> None:
    source = (PROJECT_ROOT / "apps" / "web" / "app" / "AtanorUserStatusCard.tsx").read_text(encoding="utf-8")

    assert "NeuralEmotionPanel" not in source
    assert "agentic-os-neural-gauge" not in source
    assert "/api/neural-emotion/snapshot" in source
