from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_router
from app.routers.agentic_micro_os import router
from packages.agentic_micro_os.operator_confirm import FULL_HOST_CONFIRMATION_PHRASE
from packages.agentic_micro_os.permission_gate import gate_for_test


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_permission_tier_defaults_to_safe_draft_proposal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate_for_test(tmp_path))
    payload = _client().get("/api/agentic-os/permission/tier").json()

    assert payload["tier"] in {"DRAFT_PROPOSAL", "OBSERVE_ONLY"}
    assert payload["tier4_active"] is False
    assert payload["external_llm"] is False
    assert payload["external_sllm"] is False


def test_full_host_api_rejects_phrase_boolean_authority(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate_for_test(tmp_path))
    client = _client()

    wrong_phrase = client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={"enabled_by": "owner", "typed_phrase": "enable", "duration_sec": 600},
    ).json()
    no_duration = client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={"enabled_by": "owner", "typed_phrase": FULL_HOST_CONFIRMATION_PHRASE, "duration_sec": 0},
    ).json()

    assert wrong_phrase["allowed"] is False
    assert no_duration["allowed"] is False
    assert (
        wrong_phrase["reason"]
        == "signed_operator_run_lease_required"
    )
    assert wrong_phrase["tier4_active"] is False


def test_full_host_phrase_cannot_enable_any_sub_switch(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate_for_test(tmp_path))
    client = _client()
    enabled = client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={
            "enabled_by": "owner",
            "typed_phrase": FULL_HOST_CONFIRMATION_PHRASE,
            "duration_sec": 600,
            "sub_switches": {"shell": True, "git_push": False, "local_brain_write": False},
        },
    ).json()

    shell = client.post("/api/agentic-os/permission/verify-action", json={"scope": "shell", "action": "echo"}).json()
    git_push = client.post("/api/agentic-os/permission/verify-action", json={"scope": "git_push", "action": "git push"}).json()
    local_write = client.post("/api/agentic-os/permission/verify-action", json={"scope": "local_brain_write"}).json()
    assert enabled["allowed"] is False
    assert (
        enabled["reason"] == "signed_operator_run_lease_required"
    )
    assert shell["allowed"] is False
    assert git_push["allowed"] is False
    assert local_write["allowed"] is False
    assert enabled["tier4_active"] is False


def test_denied_legacy_enable_does_not_revoke_existing_session(
    monkeypatch,
    tmp_path,
) -> None:
    gate = gate_for_test(tmp_path)
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate)
    enabled = gate.enable_full_host(
        enabled_by="isolated_test_boundary",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches={"shell": True},
    )
    session_id = gate.status()["session"]["session_id"]

    denied = _client().post(
        "/api/agentic-os/permission/full-host/enable",
        json={
            "enabled_by": "untrusted_request",
            "typed_phrase": "wrong",
            "duration_sec": 1,
        },
    ).json()

    assert enabled["allowed"] is True
    assert denied["allowed"] is False
    assert gate.status()["tier4_active"] is True
    assert gate.status()["session"]["session_id"] == session_id


def test_emergency_stop_blocks_verified_action(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate_for_test(tmp_path))
    client = _client()
    attempted = client.post(
        "/api/agentic-os/permission/full-host/enable",
        json={
            "enabled_by": "owner",
            "typed_phrase": FULL_HOST_CONFIRMATION_PHRASE,
            "duration_sec": 600,
            "sub_switches": {"shell": True},
        },
    ).json()
    stop = client.post("/api/agentic-os/permission/full-host/emergency-stop", json={"reason": "test stop"}).json()
    shell = client.post("/api/agentic-os/permission/verify-action", json={"scope": "shell", "action": "echo"}).json()

    assert attempted["allowed"] is False
    assert stop["allowed"] is False
    assert shell["allowed"] is False
    assert "emergency stop" in shell["reason"]
