from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_router
from app.routers.agentic_micro_os import router
from packages.agentic_micro_os.operator_confirm import FULL_HOST_CONFIRMATION_PHRASE
from packages.agentic_micro_os.permission_gate import AutonomySubSwitches, gate_for_test
from packages.agentic_micro_os.scoped_patch_executor import APPLY_CONFIRMATION, ROLLBACK_CONFIRMATION, ScopedPatchExecutor


def _client(monkeypatch, tmp_path) -> TestClient:
    gate = gate_for_test(tmp_path)
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate)
    monkeypatch.setattr(agentic_router, "HOST_EXECUTOR", agentic_router._make_host_executor(tmp_path))
    monkeypatch.setattr(
        agentic_router,
        "SCOPED_PATCH_EXECUTOR",
        ScopedPatchExecutor(gate=gate, project_root=tmp_path, backup_dir=tmp_path / "runtime" / "agentic_micro_os" / "scoped_patch_backups"),
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _target(tmp_path):
    path = tmp_path / "packages" / "agentic_micro_os" / "api_demo.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("VALUE = 'old'\n", encoding="utf-8")
    return path


def _payload(path, *, session_id: str = "", confirmation: str = APPLY_CONFIRMATION):
    return {
        "target_path": str(path),
        "expected_old_text": "VALUE = 'old'",
        "replacement_text": "VALUE = 'new'",
        "reason": "api scoped patch test",
        "operator_confirmation": confirmation,
        "tier_session_id": session_id,
        "required_subswitches": ["full_file_write"],
        "dry_run": False,
    }


def _enable_tier4(client: TestClient, *, full_file_write: bool = True) -> str:
    _ = client
    # The public legacy phrase endpoint is intentionally non-authoritative.
    # Exercise the scoped-patch mechanism with an isolated local gate fixture.
    payload = agentic_router.PERMISSION_GATE.enable_full_host(
        enabled_by="api_test",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches=AutonomySubSwitches(
            full_file_write=full_file_write
        ).to_dict(),
    )
    assert payload["tier4_active"] is True
    return payload["session"]["session_id"]


def test_patch_status(monkeypatch, tmp_path) -> None:
    payload = _client(monkeypatch, tmp_path).get("/api/agentic-os/host-executor/patch/status").json()

    assert payload["available"] is True
    assert payload["host_executor_v1_scoped_only"] is True
    assert payload["production_store_mutated"] is False


def test_patch_plan_dry_run_without_mutation(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    target = _target(tmp_path)

    payload = client.post("/api/agentic-os/host-executor/patch/plan", json={**_payload(target), "dry_run": True}).json()

    assert payload["allowed"] is True
    assert "+VALUE = 'new'" in payload["diff_preview"]
    assert payload["mutation_performed"] is False
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_patch_apply_requires_tier4_full_file_write_and_confirmation(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    target = _target(tmp_path)

    outside = client.post("/api/agentic-os/host-executor/patch/apply", json=_payload(target)).json()
    session_id = _enable_tier4(client, full_file_write=False)
    no_switch = client.post("/api/agentic-os/host-executor/patch/apply", json=_payload(target, session_id=session_id)).json()
    client.post("/api/agentic-os/permission/full-host/disable", json={"operator_id": "api_test"})
    session_id = _enable_tier4(client, full_file_write=True)
    bad_phrase = client.post("/api/agentic-os/host-executor/patch/apply", json=_payload(target, session_id=session_id, confirmation="APPLY")).json()

    assert outside["applied"] is False
    assert no_switch["applied"] is False
    assert bad_phrase["applied"] is False
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_patch_apply_and_rollback(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(client)

    applied = client.post("/api/agentic-os/host-executor/patch/apply", json=_payload(target, session_id=session_id)).json()
    rollback = client.post(
        "/api/agentic-os/host-executor/patch/rollback",
        json={
            "target_path": str(target),
            "backup_path": applied["backup_path"],
            "operator_confirmation": ROLLBACK_CONFIRMATION,
            "tier_session_id": session_id,
        },
    ).json()

    assert applied["applied"] is True
    assert applied["mutation_performed"] is True
    assert applied["auto_commit"] is False
    assert applied["auto_push"] is False
    assert rollback["applied"] is True
    assert rollback["mutation_performed"] is True
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_emergency_stop_and_forbidden_paths(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(client)
    client.post("/api/agentic-os/permission/full-host/emergency-stop", json={"operator_id": "api_test", "reason": "stop"})

    stopped = client.post("/api/agentic-os/host-executor/patch/apply", json=_payload(target, session_id=session_id)).json()
    forbidden = client.post(
        "/api/agentic-os/host-executor/patch/plan",
        json={**_payload("data/cloud_brain/verified_store_v0/demo.py"), "dry_run": True},
    ).json()

    assert stopped["applied"] is False
    assert "emergency stop" in stopped["denied_reason"]
    assert forbidden["allowed"] is False
