from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import agentic_micro_os as router_module
from app.routers.agentic_micro_os import router
from packages.neural_emotion.event_bus import EVENT_BUS


def _client() -> TestClient:
    router_module.AUTONOMOUS_DAEMON.stop(reason="test_reset")
    router_module._reset_agentic_run_lease_runtime_for_tests()
    EVENT_BUS.reset(clear_events=True)
    router_module.POLICY_SCHEDULER_RUNS.clear()
    router_module.REVIEW_QUEUE.items.clear()
    router_module.REVIEW_QUEUE.decisions.clear()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_scheduler_disabled_by_default() -> None:
    payload = _client().get("/api/agentic-os/policy-scheduler/status").json()

    assert payload["enabled"] is False
    assert payload["safety_flags"]["scheduler_opt_in"] is True
    assert payload["safety_flags"]["scheduler_stoppable"] is True


def test_scheduler_start_rejects_boolean_only_authority() -> None:
    client = _client()

    denied = client.post("/api/agentic-os/policy-scheduler/start", json={"operator_confirmed": False}).json()
    legacy_boolean = client.post("/api/agentic-os/policy-scheduler/start", json={"operator_confirmed": True, "max_cycles": 2}).json()

    assert denied["allowed"] is False
    assert legacy_boolean["allowed"] is False
    assert denied["reason"] == "signed_operator_run_lease_required"
    assert legacy_boolean["reason"] == "signed_operator_run_lease_required"


def test_scheduler_stop_works() -> None:
    client = _client()
    router_module.POLICY_SCHEDULER.start(operator_confirmed=True)

    stopped = client.post("/api/agentic-os/policy-scheduler/stop", json={"reason": "api_test_stop"}).json()

    assert stopped["enabled"] is False
    assert stopped["stopped_reason"] == "api_test_stop"


def test_scheduler_tick_requires_active_signed_lease() -> None:
    client = _client()

    payload = client.post("/api/agentic-os/policy-scheduler/tick").json()

    assert payload["ran"] is False
    assert payload["allowed"] is False
    assert payload["reason"] == "signed_operator_run_lease_required"
    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False
    assert payload["auto_commit"] is False
    assert payload["auto_push"] is False

def test_scheduler_status_has_no_mutation_flags() -> None:
    payload = _client().get("/api/agentic-os/policy-scheduler/status").json()

    assert payload["local_brain_write"] is False
    assert payload["production_store_mutated"] is False
    assert payload["candidate_promotion"] is False
    assert payload["auto_commit"] is False
    assert payload["auto_push"] is False
