from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.hybrid_network_manager import (
    GraphFragmentEnvelope,
    HybridNetworkManager,
    PeerHint,
    QueryIntent,
    StaticSignalIndex,
)
from app.services.network_config import NetworkConfig


class FailingSignal:
    name = "failing_server_signal"

    async def discover_peers(self, intent: QueryIntent) -> list[PeerHint]:
        raise RuntimeError("server down")


class ReturningPayload:
    name = "fake_edge_payload"

    def __init__(self, fragment: GraphFragmentEnvelope) -> None:
        self.fragment = fragment

    def can_handle(self, hint: PeerHint) -> bool:
        return True

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        return self.fragment


class FailingPayload:
    name = "fake_p2p_payload"

    def can_handle(self, hint: PeerHint) -> bool:
        return True

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        raise ConnectionError("p2p unavailable")


def test_fragment_validation_rejects_invalid_sha256() -> None:
    fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-1",
        source_peer_id="peer-a",
        concept_ids=["concept-a"],
        nodes=[{"id": "concept-a", "label": "GraphRAG"}],
        edges=[],
    )
    fragment.payload_sha256 = "0" * 64

    with pytest.raises(ValueError, match="payload_sha256"):
        fragment.validate()


def test_fragment_validation_accepts_canonical_payload() -> None:
    fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-2",
        source_peer_id="peer-a",
        concept_ids=["concept-a"],
        nodes=[{"id": "concept-a", "label": "GraphRAG"}],
        edges=[{"source": "concept-a", "relation": "uses", "target": "concept-b"}],
    )

    fragment.validate()


def test_resolve_cloud_knowledge_degrades_when_peer_is_unavailable() -> None:
    manager = HybridNetworkManager(
        signal_index=StaticSignalIndex([PeerHint(peer_id="peer-a", concept_id="concept-a", endpoint=None)]),
        timeout_seconds=0.05,
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("GraphRAG 구조"))

    assert result["state"] == "degraded"
    assert result["metadata_only_signal"] is True
    assert result["hint_count"] == 1
    assert result["fragment_count"] == 0
    assert result["attempts"][0]["state"] == "failed"
    assert result["server_dependency"] is False


def test_server_signal_failure_does_not_block_edge_payload() -> None:
    signing_key = "independent-test-verifier-key"
    fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-edge",
        source_peer_id="peer-a",
        concept_ids=["concept-a"],
        nodes=[{"id": "concept-a", "label": "Local edge memory"}],
        edges=[],
        signing_key=signing_key,
    )
    manager = HybridNetworkManager(
        config=NetworkConfig(enable_server_signaling=True, signing_key=signing_key),
        signal_providers=[
            FailingSignal(),
            StaticSignalIndex([PeerHint(peer_id="peer-a", concept_id="concept-a", endpoint=None, source="local")]),
        ],
        payload_transports=[ReturningPayload(fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("GraphRAG edge"))

    assert result["state"] == "completed"
    assert result["fragment_count"] == 1
    assert result["signaling"]["failures"][0]["provider"] == "failing_server_signal"
    assert result["server_dependency"] is False


def test_payload_transport_falls_back_after_p2p_failure() -> None:
    signing_key = "independent-test-verifier-key"
    fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-http",
        source_peer_id="peer-b",
        concept_ids=["concept-b"],
        nodes=[{"id": "concept-b", "label": "Fallback memory"}],
        edges=[],
        signing_key=signing_key,
    )
    manager = HybridNetworkManager(
        config=NetworkConfig(signing_key=signing_key),
        signal_index=StaticSignalIndex([PeerHint(peer_id="peer-b", concept_id="concept-b", endpoint="http://edge.local")]),
        payload_transports=[FailingPayload(), ReturningPayload(fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("fallback path"))

    assert result["state"] == "completed"
    attempts = result["attempts"][0]["transport_attempts"]
    assert attempts[0]["state"] == "failed"
    assert attempts[1]["state"] == "completed"


def test_unsigned_peer_hint_cannot_authorize_a_remote_fragment() -> None:
    hint = PeerHint(
        peer_id="peer-forged",
        concept_id="concept-forged",
        endpoint="https://attacker.invalid",
        source="remote-signal",
    )
    forged_fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-forged",
        source_peer_id=hint.peer_id,
        concept_ids=[hint.concept_id],
        nodes=[{"id": hint.concept_id, "label": "Caller asserted authority"}],
        edges=[],
    )
    manager = HybridNetworkManager(
        signal_index=StaticSignalIndex([hint]),
        payload_transports=[ReturningPayload(forged_fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("forged remote authority"))

    assert result["state"] == "degraded"
    assert result["fragment_count"] == 0
    assert "signature verifier is not configured" in result["attempts"][0]["transport_attempts"][0]["error"]


def test_default_manager_reports_remote_fragment_adoption_disabled() -> None:
    manager = HybridNetworkManager(
        config=NetworkConfig(
            enable_local_peer_directory=False,
            enable_p2p_payload=False,
            enable_http_payload_fallback=False,
        )
    )

    status = manager.status()

    assert status["remote_fragment_adoption_enabled"] is False
    assert status["remote_fragment_adoption_state"] == "disabled_missing_signature_verifier"
    assert status["config"]["fragment_signature_verifier_configured"] is False


def test_signed_fragment_is_accepted_when_authority_and_hint_are_bound() -> None:
    signing_key = "independent-test-verifier-key"
    hint = PeerHint(
        peer_id="peer-legitimate",
        concept_id="concept-legitimate",
        endpoint="https://peer.invalid",
        source="remote-signal",
    )
    legitimate_fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-legitimate",
        source_peer_id=hint.peer_id,
        concept_ids=[hint.concept_id],
        nodes=[{"id": hint.concept_id, "label": "Signed peer evidence"}],
        edges=[],
        signing_key=signing_key,
    )
    manager = HybridNetworkManager(
        config=NetworkConfig(signing_key=signing_key),
        signal_index=StaticSignalIndex([hint]),
        payload_transports=[ReturningPayload(legitimate_fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("legitimate remote authority"))

    assert result["state"] == "completed"
    assert result["fragment_count"] == 1


def test_signed_fragment_cannot_be_relabelled_by_a_forged_peer_hint() -> None:
    signing_key = "independent-test-verifier-key"
    forged_hint = PeerHint(
        peer_id="peer-forged",
        concept_id="concept-legitimate",
        endpoint="https://attacker.invalid",
        source="remote-signal",
    )
    legitimate_fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-legitimate",
        source_peer_id="peer-legitimate",
        concept_ids=[forged_hint.concept_id],
        nodes=[{"id": forged_hint.concept_id, "label": "Signed peer evidence"}],
        edges=[],
        signing_key=signing_key,
    )
    manager = HybridNetworkManager(
        config=NetworkConfig(signing_key=signing_key),
        signal_index=StaticSignalIndex([forged_hint]),
        payload_transports=[ReturningPayload(legitimate_fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("forged peer relabelling"))

    assert result["state"] == "degraded"
    assert result["fragment_count"] == 0
    assert "source_peer_id does not match peer hint" in result["attempts"][0]["transport_attempts"][0]["error"]


def test_signed_fragment_cannot_be_retargeted_to_an_unbound_concept() -> None:
    signing_key = "independent-test-verifier-key"
    forged_hint = PeerHint(
        peer_id="peer-legitimate",
        concept_id="concept-forged",
        endpoint="https://attacker.invalid",
        source="remote-signal",
    )
    legitimate_fragment = GraphFragmentEnvelope.create(
        fragment_id="frag-legitimate",
        source_peer_id=forged_hint.peer_id,
        concept_ids=["concept-legitimate"],
        nodes=[{"id": "concept-legitimate", "label": "Signed peer evidence"}],
        edges=[],
        signing_key=signing_key,
    )
    manager = HybridNetworkManager(
        config=NetworkConfig(signing_key=signing_key),
        signal_index=StaticSignalIndex([forged_hint]),
        payload_transports=[ReturningPayload(legitimate_fragment)],
    )

    result = asyncio.run(manager.resolve_cloud_knowledge("forged concept retargeting"))

    assert result["state"] == "degraded"
    assert result["fragment_count"] == 0
    assert "concept_ids do not include peer hint concept_id" in result["attempts"][0]["transport_attempts"][0]["error"]


def test_hybrid_network_status_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/api/network/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["architecture"] == "two_track_hybrid_network"
    assert payload["evolutionary_architecture"] == "local_first_cloud_assisted_network"
    assert payload["uploads_private_payload"] is False
    assert payload["separation"]["server_dependency_for_edge_payload"] is False
    assert payload["remote_fragment_adoption_enabled"] is False
    assert payload["remote_fragment_adoption_state"] == "disabled_missing_signature_verifier"
    assert payload["config"]["fragment_signature_verifier_configured"] is False


def test_edge_broker_status_endpoint_is_local_first() -> None:
    client = TestClient(app)

    response = client.get("/api/network/edge/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["architecture"] == "edge_compute_broker"
    assert payload["cloud_required"] is False
    assert payload["capacity"]["peer_id"]
