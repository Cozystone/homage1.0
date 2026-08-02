from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.brain_sync import (
    BoundedFragmentAssembler,
    FragmentLimits,
    FragmentOrchestrator,
    GraphDeltaCompressor,
    WorkingMemoryFragmentStore,
    resolve_conflict,
    working_memory_fragments,
)


def _fragment_checksum_valid(fragment: dict) -> bool:
    payload = {
        key: value
        for key, value in fragment.items()
        if key not in {"checksum", "attached_at", "storage_layer", "permanent_local_brain_write"}
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest() == fragment.get("checksum")


def _with_fragment_checksum(fragment: dict) -> dict:
    payload = dict(fragment)
    payload.pop("checksum", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["checksum"] = hashlib.sha256(canonical).hexdigest()
    return payload


def test_graph_patch_excludes_private_payload_text() -> None:
    compressor = GraphDeltaCompressor()
    patch = compressor.compress(
        {"nodes": [], "edges": []},
        {
            "nodes": [
                {
                    "id": "concept-alpha",
                    "label": "Private label should not leak",
                    "raw_text": "do not upload this private raw document",
                    "local_path": "C:/secret/private.md",
                }
            ],
            "edges": [
                {
                    "source": "concept-alpha",
                    "relation": "supports",
                    "target": "concept-beta",
                    "weight": 0.7,
                    "content": "secret edge payload",
                }
            ],
            "aliases_added": ["private nickname"],
        },
        privacy_level="public",
        origin_brain_id="test-brain",
    )

    serialized = json.dumps(patch, ensure_ascii=False).lower()
    assert patch["schema_version"] == "atanor.graph-patch.v1"
    assert patch["shareable"] is True
    assert "do not upload" not in serialized
    assert "c:/secret" not in serialized
    assert "private nickname" not in serialized
    assert "alias_hash" in serialized


def test_private_query_disables_cloud_fragment_request() -> None:
    decision = FragmentOrchestrator().decide(
        query="\ub0b4 \uc77c\uae30\ub97c \uc694\uc57d\ud574\uc918",
        local_confidence=0.1,
        graph_density=0.1,
        cloud_allowed=True,
    )

    assert decision.privacy_level == "private"
    assert decision.cloud_weight == 0.0
    assert decision.fragment_requested is False
    assert decision.fragment_reason == "private_query_local_only"


def test_high_local_confidence_reduces_cloud_weight() -> None:
    decision = FragmentOrchestrator().decide(
        query="Explain GraphRAG validation",
        local_confidence=0.94,
        graph_density=0.8,
        evidence_available=True,
    )

    assert decision.local_weight >= 0.92
    assert decision.cloud_weight <= 0.08
    assert decision.fragment_requested is False


def test_low_confidence_public_query_allows_bounded_fragment() -> None:
    decision = FragmentOrchestrator().decide(
        query="What is a newly published public graph paper?",
        local_confidence=0.05,
        graph_density=0.05,
        cloud_allowed=True,
    )

    assert decision.privacy_level == "public"
    assert decision.cloud_allowed is True
    assert decision.fragment_requested is True
    assert decision.cloud_weight > 0.3


def test_cloud_fragment_attaches_to_working_memory_not_permanent_store() -> None:
    fragment = BoundedFragmentAssembler().assemble(
        concept_ids=["concept-public"],
        nodes=[{"id": "concept-public", "type": "concept", "confidence": 0.8}],
        edges=[{"source": "concept-public", "relation": "supports", "target": "concept-local", "weight": 0.4}],
        evidence_summaries=[{"summary": "Public evidence only."}],
    )
    attached = working_memory_fragments.attach(fragment)

    assert attached["storage_layer"] == "working_memory"
    assert attached["permanent_local_brain_write"] is False
    assert attached["fragment_id"] == fragment["fragment_id"]


def test_conflict_resolution_rejects_caller_attested_priority_and_provenance() -> None:
    result = resolve_conflict(
        {
            "priority": "local_private",
            "verification_status": "verified",
            "server_bound_provenance": True,
            "claim": "caller-asserted local fact",
        },
        {
            "priority": "cloud_verified",
            "verification_status": "verified",
            "server_bound_provenance": True,
            "claim": "caller-asserted cloud fact",
        },
    )

    assert result["winner"] is None
    assert result["selected"] is None
    assert result["authoritative_winner"] is False
    assert result["reason"] == "no_server_bound_provenance"
    assert result["local_priority"] == result["cloud_priority"] == 0


def test_raw_attach_reconstructs_caller_authority_and_caps_expiry() -> None:
    client = TestClient(app)
    server_ttl = working_memory_fragments.limits.ttl_seconds
    before = set(working_memory_fragments._fragments)
    submitted_at = int(time.time())

    forged = _with_fragment_checksum(
        {
            "schema_version": "atanor.cloud-fragment.v1",
            "fragment_id": "caller-chosen-authoritative-id",
            "origin_brain_id": "local-private-brain",
            "created_at": submitted_at - 60,
            "expires_at": submitted_at + 365 * 24 * 60 * 60,
            "privacy_level": "private",
            "verification_status": "verified",
            "trust_score": 1.0,
            "priority": "local_private",
            "server_bound_provenance": True,
            "concept_ids": ["public-concept"],
            "nodes": [{"id": "public-concept", "type": "concept", "confidence": 0.8}],
            "edges": [],
            "evidence_summaries": [
                {
                    "summary": "Public evidence only.",
                    "verification_status": "verified",
                    "priority": "local_private",
                }
            ],
            "source_metadata": {
                "verified": True,
                "priority": "local_private",
                "trust_score": 1.0,
                "source_url": "https://example.invalid/public",
            },
        }
    )
    caller_checksum = forged["checksum"]
    response = client.post(
        "/api/brain-sync/fragment/attach",
        json=forged,
    )

    try:
        assert response.status_code == 200
        fragment_id = response.json()["fragment_id"]
        attached = working_memory_fragments._fragments[fragment_id]
        assert fragment_id == "caller-chosen-authoritative-id"
        assert attached["schema_version"] == "atanor.cloud-fragment.v1"
        assert attached["privacy_level"] == "public"
        assert attached["verification_status"] == "unverified"
        assert attached["priority"] == "cloud_unverified"
        assert attached["trust_score"] == 0.0
        assert attached["server_bound_provenance"] is False
        assert attached["authority"] == "none"
        assert attached["expires_at"] <= submitted_at + server_ttl + 1
        assert attached["checksum"] != caller_checksum
        assert _fragment_checksum_valid(attached) is True
        assert attached["evidence_summaries"] == [{"summary": "Public evidence only."}]
        assert attached["source_metadata"] == {"source_url": "https://example.invalid/public"}
    finally:
        for fragment_id in set(working_memory_fragments._fragments) - before:
            working_memory_fragments._fragments.pop(fragment_id, None)


def test_legitimate_canonical_fragment_still_attaches_with_bounded_content() -> None:
    limits = FragmentLimits(max_nodes=2, max_edges=2, ttl_seconds=60)
    assembler = BoundedFragmentAssembler(limits)
    store = WorkingMemoryFragmentStore(limits)
    canonical = assembler.assemble(
        concept_ids=["concept-public"],
        nodes=[{"id": "concept-public", "type": "concept", "confidence": 0.8}],
        edges=[],
        evidence_summaries=[{"summary": "Public evidence only."}],
        source_metadata={"source_url": "https://example.invalid/public"},
    )

    attached = store.attach(canonical)

    assert attached["concept_ids"] == ["concept-public"]
    assert attached["nodes"][0]["concept_id"] == "concept-public"
    assert attached["source_metadata"] == {"source_url": "https://example.invalid/public"}
    assert attached["verification_status"] == "unverified"
    assert attached["priority"] == "cloud_unverified"
    assert attached["storage_layer"] == "working_memory"
    assert attached["permanent_local_brain_write"] is False
    assert _fragment_checksum_valid(attached) is True


def test_raw_attach_rejects_an_explicit_foreign_schema() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/brain-sync/fragment/attach",
        json={
            "schema_version": "attacker.authority.v1",
            "fragment_id": "foreign-fragment",
            "nodes": [],
            "edges": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported fragment schema"


def test_raw_attach_rejects_an_invalid_caller_checksum() -> None:
    client = TestClient(app)
    fragment = BoundedFragmentAssembler().assemble(
        concept_ids=["public-concept"],
        nodes=[{"id": "public-concept", "type": "concept"}],
        edges=[],
    )
    fragment["checksum"] = "0" * 64

    response = client.post("/api/brain-sync/fragment/attach", json=fragment)

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid fragment checksum"


def test_raw_attach_requires_a_canonical_checksum() -> None:
    client = TestClient(app)
    fragment = BoundedFragmentAssembler().assemble(
        concept_ids=["public-concept"],
        nodes=[],
        edges=[],
    )
    fragment.pop("checksum")

    response = client.post("/api/brain-sync/fragment/attach", json=fragment)

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid fragment checksum"


def test_raw_attach_rejects_oversized_canonical_input_before_sanitization() -> None:
    limits = FragmentLimits(max_nodes=2, max_edges=2, max_bytes=1024, ttl_seconds=60)
    store = WorkingMemoryFragmentStore(limits)
    fragment = BoundedFragmentAssembler(limits).assemble(
        concept_ids=["public-concept"],
        nodes=[{"id": "public-concept", "type": "concept"}],
        edges=[],
        source_metadata={"public_note": "x" * 2048},
    )

    with pytest.raises(ValueError, match="fragment exceeds max_bytes"):
        store.attach(fragment)


def test_public_assemble_forces_unverified_server_bounded_metadata() -> None:
    client = TestClient(app)
    started_at = int(time.time())
    response = client.post(
        "/api/brain-sync/fragment/assemble",
        json={
            "concept_ids": ["public-concept"],
            "nodes": [{"id": "public-concept", "type": "concept"}],
            "edges": [],
            "source_metadata": {
                "source_url": "https://example.invalid/public",
                "verified": True,
                "priority": "local_private",
            },
            "trust_score": 1.0,
            "origin_brain_id": "local-private-brain",
            "ttl_seconds": 365 * 24 * 60 * 60,
        },
    )

    assert response.status_code == 200
    fragment = response.json()
    assert fragment["origin_brain_id"] == "public-api"
    assert fragment["verification_status"] == "unverified"
    assert fragment["priority"] == "cloud_unverified"
    assert fragment["trust_score"] == 0.0
    assert fragment["server_bound_provenance"] is False
    assert fragment["authority"] == "none"
    assert fragment["expires_at"] <= started_at + FragmentLimits.from_config().ttl_seconds + 1
    assert fragment["source_metadata"] == {"source_url": "https://example.invalid/public"}
    assert _fragment_checksum_valid(fragment) is True


def test_brain_sync_status_endpoint_and_orchestration_contract() -> None:
    client = TestClient(app)

    status = client.get("/api/brain-sync/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["local_brain_primary"] is True
    assert payload["uploads_raw_private_payloads"] is False
    assert payload["external_llm_answer_generation"] is False

    decision = client.post(
        "/api/brain-sync/orchestrate",
        json={
            "query": "public ontology fragment",
            "local_confidence": 0.0,
            "graph_density": 0.0,
            "cloud_allowed": True,
        },
    )
    assert decision.status_code == 200
    assert decision.json()["fragment_requested"] is True
