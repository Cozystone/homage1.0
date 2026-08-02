from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import agentic_micro_os as router_module
from app.routers.agentic_micro_os import router
from packages.neural_emotion.event_bus import EVENT_BUS


def _client() -> TestClient:
    EVENT_BUS.reset(clear_events=True)
    router_module.POLICY_LOOP_RUNS.clear()
    router_module.REVIEW_QUEUE.items.clear()
    router_module.REVIEW_QUEUE.decisions.clear()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_policy_loop_status_is_proof_only() -> None:
    payload = _client().get("/api/agentic-os/policy-loop/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert payload["policy_decision"]["permission_gate_bypass"] is False
    assert payload["policy_decision"]["autonomy_tier_auto_changed"] is False


def test_policy_loop_run_once_creates_bounded_result() -> None:
    payload = _client().post("/api/agentic-os/policy-loop/run-once", json={"max_cycles": 1, "base_web_pages": 2}).json()

    assert payload["cycles_completed"] == 1
    assert payload["stopped_reason"] == "max_cycles"
    assert payload["candidate_drafts"] >= 0
    assert payload["splatra_frames"] >= 0
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False
    assert payload["auto_commit"] is False
    assert payload["auto_push"] is False


def test_policy_loop_runs_lookup() -> None:
    client = _client()
    payload = client.post("/api/agentic-os/policy-loop/run-once", json={"loop_id": "policy_api_test", "max_cycles": 1}).json()
    lookup = client.get("/api/agentic-os/policy-loop/runs/policy_api_test").json()

    assert payload["loop_id"] == "policy_api_test"
    assert lookup["run"]["loop_id"] == "policy_api_test"


def test_policy_loop_fatigue_request_rests() -> None:
    client = _client()
    EVENT_BUS.emit(source="user_action", event_type="repeated_failure", intensity=2.0)
    EVENT_BUS.emit(source="user_action", event_type="repeated_failure", intensity=2.0)
    payload = client.post("/api/agentic-os/policy-loop/run-once", json={"max_cycles": 3, "recent_failures": 5}).json()

    assert payload["final_policy"]["agent_loop"]["should_rest"] is True
    assert payload["stopped_reason"] in {"fatigue", "repeated_failure"}


def test_policy_loop_review_pressure_requests_review() -> None:
    client = _client()
    web_run = client.post("/api/agentic-os/web-explorer/open/run", json={"max_pages": 1, "per_domain_delay_sec": 0}).json()
    client.post("/api/agentic-os/review/import-web-run", json={"run_payload": web_run})
    payload = client.post(
        "/api/agentic-os/policy-loop/run-once",
        json={"max_cycles": 2, "review_queue_pressure": 0.9},
    ).json()

    assert payload["stopped_reason"] == "review_requested"
    assert payload["review_items"] >= 1
