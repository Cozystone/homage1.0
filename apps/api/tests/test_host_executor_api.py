from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.agentic_micro_os as agentic_router
from app.routers.agentic_micro_os import router
from packages.agentic_micro_os.host_executor import SAFE_TEST_TOKEN
from packages.agentic_micro_os.permission_gate import gate_for_test


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(agentic_router, "PERMISSION_GATE", gate_for_test(tmp_path))
    monkeypatch.setattr(agentic_router, "HOST_EXECUTOR", agentic_router._make_host_executor(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_host_executor_status(monkeypatch, tmp_path) -> None:
    payload = _client(monkeypatch, tmp_path).get("/api/agentic-os/host-executor/status").json()

    assert payload["available"] is True
    assert payload["proof_only"] is True
    assert "echo" in payload["allowed_v0_actions"]


def test_default_denies_shell_but_safe_diagnostics_work(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    denied = client.post("/api/agentic-os/host-executor/execute", json={"action_type": "echo", "content": "hello"}).json()
    allowed = client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "echo", "content": "hello", "safe_test_token": SAFE_TEST_TOKEN},
    ).json()

    assert denied["allowed"] is False
    assert denied["executed"] is False
    assert allowed["allowed"] is True
    assert allowed["executed"] is True


def test_temp_file_write_read_and_rejected_delete(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    write = client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "write_temp_file", "path": "api-note.txt", "content": "ok", "safe_test_token": SAFE_TEST_TOKEN},
    ).json()
    read = client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "read_text_file", "path": write["path_refs"][0], "safe_test_token": SAFE_TEST_TOKEN},
    ).json()
    delete = client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "delete_file", "path": write["path_refs"][0], "safe_test_token": SAFE_TEST_TOKEN},
    ).json()

    assert write["allowed"] is True
    assert write["mutation_performed"] is True
    assert read["stdout_excerpt"] == "ok"
    assert delete["allowed"] is False
    assert delete["executed"] is False


def test_git_commit_push_and_production_writes_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    for action in ["git_commit", "git_push", "local_brain_write", "cloud_production_write", "network_upload"]:
        payload = client.post(
            "/api/agentic-os/host-executor/execute",
            json={"action_type": action, "safe_test_token": SAFE_TEST_TOKEN},
        ).json()
        assert payload["allowed"] is False
        assert payload["executed"] is False


def test_emergency_stop_blocks_host_executor(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    client.post("/api/agentic-os/permission/full-host/emergency-stop", json={"reason": "test stop"})
    payload = client.post(
        "/api/agentic-os/host-executor/execute",
        json={"action_type": "echo", "content": "hello", "safe_test_token": SAFE_TEST_TOKEN},
    ).json()

    assert payload["allowed"] is False
    assert "emergency stop" in payload["denied_reason"]
