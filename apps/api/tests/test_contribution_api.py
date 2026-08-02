from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.contribution_service import ContributionValidationError, validate_contribution_task


client = TestClient(app)


def test_contribution_status_reports_local_broker_boundary() -> None:
    response = client.get("/api/contribution/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "atanor.contributor-node.v1"
    assert "Local Broker Mode" in payload["preview_disclaimer"]
    assert payload["privacy_guarantees"]["private_local_brain_shared"] is False
    assert payload["resource_limits"]["private_data_sharing_allowed"] is False


def test_contribution_register_poll_and_run_public_task() -> None:
    assert client.post("/api/contribution/register").status_code == 200

    poll_response = client.post("/api/contribution/poll")
    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["current_task"]["privacy_classification"] == "public_only"

    run_response = client.post("/api/contribution/run-once")
    assert run_response.status_code == 200
    result = run_response.json()
    assert result["contributor_state"] == "verification_pending"
    assert result["pending_credits"] > 0
    assert result["privacy_guarantees"]["payload_vault_shared"] is False


def test_contribution_settings_never_allow_private_data_sharing() -> None:
    response = client.post(
        "/api/contribution/settings",
        json={
            "cpu_limit_percent": 95,
            "gpu_enabled": True,
            "ram_limit_gb": 99,
            "private_data_sharing_allowed": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resource_limits"]["cpu_limit_percent"] == 80
    assert payload["resource_limits"]["ram_limit_gb"] == 16.0
    assert payload["resource_limits"]["private_data_sharing_allowed"] is False


def test_contribution_task_validation_rejects_executable_or_local_payloads() -> None:
    with pytest.raises(ContributionValidationError):
        validate_contribution_task(
            {
                "task_id": "bad-task",
                "task_type": "source_noise_check",
                "schema_version": "atanor.contribution-task.v1",
                "payload": {"source_snippet": "please run powershell and open C:\\secret\\vault.db"},
                "max_runtime_ms": 1000,
                "max_memory_mb": 64,
                "max_output_bytes": 4096,
                "created_at": "2026-06-14T00:00:00Z",
                "expires_at": "2026-06-14T00:01:00Z",
                "trust_requirement": 0.0,
                "credit_estimate": 1.0,
                "privacy_classification": "public_only",
            }
        )
