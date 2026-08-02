from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cloud_broker_client import CloudBrokerClient, CloudBrokerConfig, CloudBrokerError, peer_id_hash_for_node, public_fragment_from_text
from app.services.contribution_service import ContributionService, RemoteCloudBroker


client = TestClient(app)


class FakeRemoteClient:
    def __init__(self, *, fail_status: bool = False) -> None:
        self.fail_status = fail_status
        self.submitted: list[dict] = []

    def status(self) -> dict:
        if self.fail_status:
            raise CloudBrokerError("offline")
        return {"service": "atanor-cloud-brain-broker", "mode": "dev", "status": "ok"}

    def register_node(self, node_payload: dict) -> dict:
        return {"accepted": True, "node_id": node_payload["node_id"], "broker_state": "remote_connected"}

    def heartbeat(self, node_id: str, status_payload: dict | None = None) -> dict:
        return {"accepted": True, "node_id": node_id, "broker_state": "remote_connected"}

    def poll_tasks(self, node_id: str, capabilities: dict | None = None) -> dict:
        assert len(capabilities or {}) >= 0
        return {
            "state": "task_available",
            "task": {
                "task_id": "remote-public-task-001",
                "task_type": "public_fragment_validation",
                "schema_version": "atanor.contribution-task.v1",
                "payload": {"fragment_edges": [{"source": "GraphRAG", "predicate": "uses", "target": "Evidence"}]},
                "max_runtime_ms": 1500,
                "max_memory_mb": 64,
                "max_output_bytes": 4096,
                "created_at": "2026-06-14T00:00:00Z",
                "expires_at": "2026-06-14T00:10:00Z",
                "trust_requirement": 0.0,
                "credit_estimate": 1.0,
                "privacy_classification": "public_only",
            },
            "broker_state": "remote_connected",
        }

    def submit_task(self, result_payload: dict) -> dict:
        self.submitted.append(result_payload)
        assert result_payload["peer_id_hash"] == peer_id_hash_for_node(result_payload["node_id"])
        return {
            "accepted": True,
            "state": "verification_pending",
            "broker_state": "remote_connected",
            "fragment_id": "frag_abc123",
            "content_hash": "abc123",
            "verification_state": "single_peer_pending",
            "storage_backend": "kv",
        }

    def credits(self, node_id: str) -> dict:
        return {"credits": [], "broker_state": "remote_connected"}

    def network(self) -> dict:
        return {"network_state": "active_single_peer", "active_peers": 1, "broker_state": "remote_connected"}

    def peers(self) -> dict:
        return {"peers": [{"peer_id_hash": "hash", "state": "active"}], "broker_state": "remote_connected"}


class OmittedAcceptanceRemoteClient(FakeRemoteClient):
    def submit_task(self, result_payload: dict) -> dict:
        self.submitted.append(result_payload)
        assert result_payload["peer_id_hash"] == peer_id_hash_for_node(result_payload["node_id"])
        return {
            "state": "verification_pending",
            "broker_state": "remote_connected",
            "fragment_id": "frag_without_acceptance",
            "verification_state": "single_peer_pending",
        }


def test_cloud_broker_config_reads_remote_env(monkeypatch) -> None:
    monkeypatch.setenv("ATANOR_CLOUD_MODE", "remote")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://example.execute-api.ap-northeast-2.amazonaws.com/dev")
    monkeypatch.setenv("ATANOR_CLOUD_API_KEY", "secret")
    monkeypatch.setenv("ATANOR_NODE_ID", "atanor-test-node")
    monkeypatch.setenv("ATANOR_CONTRIBUTION_ENABLED", "true")

    config = CloudBrokerConfig.from_env()

    assert config.cloud_mode == "remote"
    assert config.remote_enabled is True
    assert config.api_key == "secret"
    assert config.node_id == "atanor-test-node"
    assert config.contribution_enabled is True


def test_cloud_broker_client_rejects_private_fragment_payload() -> None:
    config = CloudBrokerConfig(cloud_mode="remote", endpoint="https://example.execute-api.ap-northeast-2.amazonaws.com/dev")
    broker = CloudBrokerClient(config)

    with pytest.raises(CloudBrokerError):
        broker.put_fragment(
            {
                "fragment_id": "bad",
                "raw_payload_exported": False,
                "nodes": [{"node_hash": "abc", "raw_text": "private local document"}],
                "edges": [],
            }
        )


def test_peer_hash_is_stable_and_non_raw_node_id() -> None:
    first = peer_id_hash_for_node("atanor-test-node")
    second = peer_id_hash_for_node("atanor-test-node")

    assert first == second
    assert first != "atanor-test-node"
    assert len(first) == 64


def test_public_fragment_builder_exports_summary_not_raw_payload() -> None:
    fragment = public_fragment_from_text(
        text="GraphRAG validates public evidence through Ghost Shell hashes.",
        source_url="https://example.com/public",
        source_peer_id="atanor-test-node",
    )

    assert fragment["raw_payload_exported"] is False
    assert fragment["nodes"]
    assert "raw_text" not in fragment["nodes"][0]
    assert fragment["source_metadata"]["raw_payload_exported"] is False


def test_contribution_service_can_use_remote_broker() -> None:
    service = ContributionService(broker=RemoteCloudBroker(client=FakeRemoteClient()))  # type: ignore[arg-type]

    registered = service.register()
    assert registered["broker_state"] == "remote_connected"

    heartbeat = service.heartbeat()
    assert heartbeat["broker_state"] == "remote_connected"

    polled = service.poll_public_task()
    assert polled["current_task"]["privacy_classification"] == "public_only"

    result = service.run_current_task()
    assert result["broker_state"] == "remote_connected"
    assert result["contributor_state"] == "verification_pending"
    assert result["pending_credits"] > 0
    assert result["confirmed_credits"] == 0
    assert result["last_remote_submission"]["accepted"] is True
    assert result["last_remote_submission"]["verification_state"] == "single_peer_pending"


def test_remote_omission_cannot_default_to_accepted_pending_credit() -> None:
    service = ContributionService(
        broker=RemoteCloudBroker(
            client=OmittedAcceptanceRemoteClient(),
        )
    )  # type: ignore[arg-type]

    service.register()
    service.poll_public_task()
    result = service.run_current_task()

    assert "accepted" not in result["last_remote_submission"]
    assert result["pending_credits"] == 0
    assert result["confirmed_credits"] == 0
    assert result["node"]["total_tasks_completed"] == 0
    assert result["node"]["total_tasks_rejected"] == 1
    assert service.credits == []


def test_contribution_service_reports_remote_error_honestly() -> None:
    service = ContributionService(broker=RemoteCloudBroker(client=FakeRemoteClient(fail_status=True)))  # type: ignore[arg-type]

    status = service.get_status()

    assert status["broker_state"] == "remote_error"
    assert "offline" in status["last_error"]


def test_cloud_brain_status_reports_remote_connected(monkeypatch) -> None:
    class FakeCloudClient:
        def __init__(self, _config):
            pass

        def status(self):
            return {"service": "atanor-cloud-brain-broker", "mode": "dev", "status": "ok"}

    monkeypatch.setenv("ATANOR_CLOUD_MODE", "remote")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://example.execute-api.ap-northeast-2.amazonaws.com/dev")
    monkeypatch.setattr("app.routers.cloud_brain.CloudBrokerClient", FakeCloudClient)

    response = client.get("/api/cloud-brain/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cloud_mode"] == "remote"
    assert payload["broker_state"] == "remote_connected"
    assert payload["public_cloud_backend_enabled"] is True


def test_cloud_brain_status_reports_remote_error(monkeypatch) -> None:
    class FailingCloudClient:
        def __init__(self, _config):
            pass

        def status(self):
            raise CloudBrokerError("network down")

    monkeypatch.setenv("ATANOR_CLOUD_MODE", "remote")
    monkeypatch.setenv("ATANOR_CLOUD_ENDPOINT", "https://example.execute-api.ap-northeast-2.amazonaws.com/dev")
    monkeypatch.setattr("app.routers.cloud_brain.CloudBrokerClient", FailingCloudClient)

    response = client.get("/api/cloud-brain/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cloud_mode"] == "remote"
    assert payload["broker_state"] == "remote_error"
    assert "network down" in payload["remote_error"]
