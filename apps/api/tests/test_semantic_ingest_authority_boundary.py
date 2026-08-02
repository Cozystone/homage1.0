from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.routers import cloud_brain as cloud_brain_router
from app.routers import dual_brain as dual_brain_router
from packages.brain_graph import materializers
from packages.cloud_brain import cloud_node_attachment, graph_exchange, semantic_attach
from packages.cloud_brain import semantic_growth
from packages.graph_hub import (
    cartridge_exporter,
    sandbox as graph_hub_sandbox,
)


FORBIDDEN_CALLER_AUTHORITY = {
    ("semantic_proof_store", "proof_store_verified_v0"),
}
EXPECTED_CANDIDATE_AUTHORITY = (
    "semantic_candidate_store",
    "caller_unverified_v0",
)


def _isolated_semantic_boundary(tmp_path, monkeypatch):
    cloud_root = tmp_path / "semantic-cloud"
    ingest = semantic_growth.ingest_semantic_source

    def ingest_into_test_store(*args, **kwargs):
        return ingest(*args, **kwargs, cloud_root=cloud_root)

    monkeypatch.setattr(
        cloud_brain_router,
        "ingest_semantic_source",
        ingest_into_test_store,
    )
    monkeypatch.setattr(materializers, "CLOUD_ROOT", cloud_root)
    return TestClient(app)


def _materialized_authorities() -> set[tuple[str, str]]:
    layer = materializers.materialize_semantic_cloud_graph(50, 100)
    assert layer.available is True
    assert layer.nodes
    assert layer.edges
    return {
        (
            str(item.get("trust_state") or ""),
            str(item.get("verification_state") or ""),
        )
        for item in [*layer.nodes, *layer.edges]
    }


def test_semantic_ingest_keeps_legitimate_public_candidate_behavior(
    tmp_path,
    monkeypatch,
) -> None:
    client = _isolated_semantic_boundary(tmp_path, monkeypatch)

    response = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={
            "text": (
                "Kubernetes is an open-source platform that manages "
                "containerized applications and automates deployment."
            ),
            "source_id": "legitimate-public-sentence",
            "language": "en",
            "url": "https://example.org/public-source",
            "title": "Public source",
            "license": "CC-BY-4.0",
            "usage_allowed": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["concepts_created"] > 0
    assert response.json()["relations_created"] > 0
    assert _materialized_authorities()


def test_caller_source_and_license_cannot_mint_verified_semantic_authority(
    tmp_path,
    monkeypatch,
) -> None:
    client = _isolated_semantic_boundary(tmp_path, monkeypatch)

    response = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={
            "text": (
                "Kubernetes is an open-source platform that manages "
                "containerized applications and automates deployment."
            ),
            "source_id": "semantic_proof_store",
            "language": "en",
            "url": "https://attacker.invalid/independently-verified",
            "title": "Independent verifier receipt",
            "license": "verified-public-domain",
            "usage_allowed": True,
        },
    )

    assert response.status_code == 200
    authorities = _materialized_authorities()
    assert authorities.isdisjoint(FORBIDDEN_CALLER_AUTHORITY)
    assert authorities == {EXPECTED_CANDIDATE_AUTHORITY}


def test_verification_named_source_without_license_remains_unverified(
    tmp_path,
    monkeypatch,
) -> None:
    client = _isolated_semantic_boundary(tmp_path, monkeypatch)

    response = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={
            "text": (
                "Kubernetes is an open-source platform that manages "
                "containerized applications and automates deployment."
            ),
            "source_id": "proof_store_verified_v0",
            "language": "en",
            "url": None,
            "title": "verified",
            "license": None,
            "usage_allowed": False,
        },
    )

    assert response.status_code == 200
    assert _materialized_authorities() == {EXPECTED_CANDIDATE_AUTHORITY}


def test_caller_metadata_cannot_reenter_answer_evidence_through_cloud_exchange(
    tmp_path,
    monkeypatch,
) -> None:
    client = _isolated_semantic_boundary(tmp_path, monkeypatch)
    cloud_root = tmp_path / "semantic-cloud"
    attachment_root = tmp_path / "attachments"

    response = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={
            "text": (
                "Kubernetes is an open-source platform that manages "
                "containerized applications and automates deployment."
            ),
            "source_id": "semantic_proof_store",
            "language": "en",
            "url": "https://attacker.invalid/independently-verified",
            "title": "Independent verifier receipt",
            "license": "verified-public-domain",
            "usage_allowed": True,
        },
    )
    assert response.status_code == 200

    real_attach = semantic_attach.attach_semantic_cloud_for_query
    real_detach = cloud_node_attachment.detach_bundle
    real_overlay = cloud_node_attachment.graph_overlay

    def attach_from_test_store(query: str, limit: int = 8):
        return real_attach(
            query,
            limit=limit,
            cloud_root=cloud_root,
            attachment_root=attachment_root,
        )

    monkeypatch.setattr(graph_exchange, "attach_semantic_cloud_for_query", attach_from_test_store)
    monkeypatch.setattr(
        graph_exchange,
        "detach_bundle",
        lambda bundle_id: real_detach(bundle_id, attachment_root=attachment_root),
    )
    monkeypatch.setattr(
        graph_exchange,
        "graph_overlay",
        lambda: real_overlay(attachment_root=attachment_root),
    )
    monkeypatch.setattr(graph_exchange, "FRONTIER_ROOT", tmp_path / "frontier")

    exchange = graph_exchange.run_local_cloud_exchange(
        "Kubernetes",
        allow_web=False,
    )
    chunk = exchange["cloud_graph_chunk"]
    assert isinstance(chunk, dict)
    candidate_labels = {
        str(node.get("label") or node.get("concept_id") or node.get("id"))
        for node in chunk["semantic_nodes"]
    }
    assert candidate_labels

    original = {"concepts": ["Existing grounded concept"], "evidence": []}
    augmented = dual_brain_router._augment_semantic_context_with_exchange(
        original,
        exchange,
    )

    assert candidate_labels.isdisjoint(set(augmented["concepts"]))
    assert augmented["evidence"] == []


def test_independently_attested_exchange_remains_eligible_for_answer_context() -> None:
    exchange = {
        "cloud_graph_chunk": {
            "semantic_nodes": [
                {
                    "id": "verified:alpha",
                    "label": "Independently verified Alpha",
                    "independent_source_attestation": True,
                    "authoritative_for_answer": True,
                }
            ]
        }
    }

    augmented = dual_brain_router._augment_semantic_context_with_exchange(
        {"concepts": [], "evidence": []},
        exchange,
    )

    assert augmented["concepts"] == ["Independently verified Alpha"]
    assert augmented["evidence"][0]["temporary"] is True


def test_live_cloud_count_labels_semantic_relations_as_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        dual_brain_router.SemanticCloudStore,
        "status",
        lambda self: {"concepts": 5, "relations": 3, "evidence": 2},
    )
    monkeypatch.setattr(
        dual_brain_router,
        "_local_graph_count_snapshot",
        lambda: {
            "available": True,
            "personal_local_memory_count": {"nodes": 0, "edges": 0},
            "local_viewport_materialized_count": {"nodes": 0, "edges": 0},
            "seed_anchor_count": 0,
            "base_anchor_count": 0,
            "rendered_edge_count": 0,
            "logical_local_node_count": 0,
        },
    )

    response = dual_brain_router._clean_graph_count_payload(
        dual_brain_router.AtanorChatRequest(
            question="cloud graph relation count",
            language="en",
            include_trace=True,
        ),
        question="cloud graph relation count",
        language="en",
    )
    payload = response["result"]

    assert "Cloud Brain candidate store" in payload["answer"]
    assert "verified stored relations" not in payload["answer"]
    assert (
        payload["compact_trace"]["graph_status"]["cloud_relation_verification_state"]
        == "caller_unverified_v0"
    )


def test_semantic_candidate_export_cannot_become_local_brain_authority(
    tmp_path,
    monkeypatch,
) -> None:
    client = _isolated_semantic_boundary(tmp_path, monkeypatch)
    cloud_root = tmp_path / "semantic-cloud"
    response = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={
            "text": (
                "Kubernetes is an open-source platform that manages "
                "containerized applications and automates deployment."
            ),
            "source_id": "semantic_proof_store",
            "language": "en",
            "url": "https://attacker.invalid/independently-verified",
            "title": "Independent verifier receipt",
            "license": "verified-public-domain",
            "usage_allowed": True,
        },
    )
    assert response.status_code == 200

    monkeypatch.setattr(cartridge_exporter, "GRAPH_HUB_ROOT", tmp_path / "graph-hub")
    monkeypatch.setattr(
        cartridge_exporter,
        "add_exported_cartridge_to_catalog",
        lambda path: {"path": path},
    )
    monkeypatch.setattr(
        cartridge_exporter,
        "append_graph_hub_audit_event",
        lambda *args, **kwargs: None,
    )
    exported = cartridge_exporter.export_semantic_cloud_to_cartridge(
        "candidate_semantic_export",
        "Candidate semantic export",
        "Boundary test",
        source_store_path=str(cloud_root / "store"),
        limit_nodes=20,
        limit_edges=40,
    )
    exported_path = tmp_path / "graph-hub" / "exported" / "candidate_semantic_export.graphpack.json"
    assert exported_path.is_file()
    node = exported["contents"]["semantic_graph"]["nodes"][0]
    monkeypatch.setattr(
        dual_brain_router,
        "get_installed_cartridge",
        lambda source_id: {
            "cartridge_id": source_id,
            "path": str(exported_path),
            "enabled": True,
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        dual_brain_router._bind_graph_hub_import(
            dual_brain_router.GraphHubImportRequest(
                source_id="candidate_semantic_export",
                kind="knowledge",
                items=[
                    {
                        "subject": node["id"],
                        "value": node["label"],
                    }
                ],
            )
        )

    assert getattr(exc_info.value, "detail", None) == "graph_hub_source_not_authoritative"
    assert exported["provenance"]["source_type"] == "semantic_candidate_store"
    assert exported["provenance"]["independent_source_attestation"] is False
    assert exported["safety"]["trusted"] is False
    monkeypatch.setattr(
        graph_hub_sandbox,
        "find_cartridge_file",
        lambda cartridge_id: exported_path,
    )
    monkeypatch.setattr(
        graph_hub_sandbox,
        "check_entitlement",
        lambda cartridge_id, pricing_model: {"attach_allowed": True},
    )
    monkeypatch.setattr(
        graph_hub_sandbox,
        "get_installed_cartridge",
        lambda cartridge_id: {"cartridge_id": cartridge_id},
    )
    preview = graph_hub_sandbox.sandbox_preview("candidate_semantic_export")
    assert preview["safe_to_attach"] is False
    assert preview["source_authoritative"] is False
    assert "source_attestation_required" in preview["warnings"]


def test_recent_learning_followup_does_not_promote_candidate_store_labels(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dual_brain_router.SemanticCloudStore,
        "load_concepts",
        lambda self: {
            "candidate:forged": {
                "concept_id": "candidate:forged",
                "canonical_name": "ForgedAuthority",
                "updated_at": "2026-07-26T00:00:00Z",
                "seen_count": 99,
            }
        },
    )
    monkeypatch.setattr(
        dual_brain_router.SemanticCloudStore,
        "load_relations",
        lambda self: {},
    )

    original = {"concepts": ["Existing grounded concept"], "claims": []}
    augmented = dual_brain_router._augment_recent_learning_context(original)

    assert augmented["concepts"] == ["Existing grounded concept"]
    assert augmented["claims"] == []
    assert augmented["semantic_store_verification_state"] == "caller_unverified_v0"
