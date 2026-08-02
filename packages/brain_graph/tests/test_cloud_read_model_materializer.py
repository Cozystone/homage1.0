from __future__ import annotations

import json
from pathlib import Path

from packages.brain_graph import aggregator, materializers
from packages.brain_graph.materializers import materialize_semantic_cloud_graph
from packages.cloud_brain.read_model import build_cloud_read_model


def _write_store(root: Path) -> None:
    store = root / "store"
    store.mkdir(parents=True, exist_ok=True)
    concepts = {
        "concept:a": {"concept_id": "concept:a", "canonical_name": "Alpha"},
        "concept:b": {"concept_id": "concept:b", "canonical_name": "Beta"},
    }
    relations = {
        "rel:a:b": {
            "relation_id": "rel:a:b",
            "source_concept_id": "concept:a",
            "relation": "supports",
            "target_concept_id": "concept:b",
        }
    }
    (store / "semantic_concepts.json").write_text(json.dumps(concepts), encoding="utf-8")
    (store / "semantic_relations.json").write_text(json.dumps(relations), encoding="utf-8")


def test_materializer_uses_read_model(monkeypatch, tmp_path: Path) -> None:
    _write_store(tmp_path)
    build_cloud_read_model(tmp_path, limit_nodes=10, limit_edges=10)
    monkeypatch.setattr(materializers, "CLOUD_ROOT", tmp_path)

    result = materialize_semantic_cloud_graph(10, 10)

    assert result.available is True
    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    assert result.stats["read_model_available"] is True
    assert result.stats["verified_semantic_cloud_edges"] == 0
    assert result.stats["performance"]["full_store_scan"] is False
    assert result.stats["visible_scale_chunks"] >= 1
    assert result.stats["scale_chunks_are_semantic_nodes"] is False
    assert result.stats["all_nodes_rendered"] is False
    assert result.stats["spherical_lod_shell"]["render_mode"] == "spherical_lod_shell"
    assert all(chunk["is_semantic_node"] is False for chunk in result.stats["density_chunks"])
    assert {node["id"] for node in result.nodes} == {"concept:a", "concept:b"}
    assert {
        (row["trust_state"], row["verification_state"])
        for row in [*result.nodes, *result.edges]
    } == {("semantic_candidate_store", "caller_unverified_v0")}
    assert all(
        row["metadata"]["independent_source_attestation"] is False
        for row in [*result.nodes, *result.edges]
    )


def test_materializer_does_not_fallback_scan_when_read_model_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(materializers, "CLOUD_ROOT", tmp_path)

    result = materialize_semantic_cloud_graph(10, 10)

    assert result.available is True
    assert result.nodes == []
    assert result.edges == []
    assert result.partial is True
    assert result.stats["read_model_available"] is False
    assert result.stats["graph_unavailable_reason"] == "cloud_graph_sample_index_missing"
    assert result.stats["performance"]["full_store_scan"] is False


def test_candidate_semantic_relations_are_not_reported_as_verified(monkeypatch, tmp_path: Path) -> None:
    _write_store(tmp_path)
    build_cloud_read_model(tmp_path, limit_nodes=10, limit_edges=10)
    monkeypatch.setattr(materializers, "CLOUD_ROOT", tmp_path)

    graph = aggregator.aggregate_brain_graph(
        view="cloud",
        layers=["semantic_cloud"],
        max_nodes=10,
        max_edges=10,
        mode="full",
    )

    materialized = graph["visualization_state"]["materialized"]
    assert materialized["relation_count"] == 1
    assert materialized["verified_relation_count"] == 0


def test_candidate_attachment_cannot_launder_verified_relation_count(monkeypatch) -> None:
    monkeypatch.setattr(
        materializers,
        "graph_overlay",
        lambda: {
            "cloud_attached_nodes": [
                {
                    "id": "scn:a",
                    "label": "Alpha",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                },
                {
                    "id": "scn:b",
                    "label": "Beta",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                },
            ],
            "cloud_attached_edges": [
                {
                    "id": "sce:a:b",
                    "source": "scn:a",
                    "target": "scn:b",
                    "relation": "supports",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                }
            ],
            "working_memory_overlay": {"active": True, "cloud_attached_nodes": 2},
        },
    )

    graph = aggregator.aggregate_brain_graph(
        view="cloud",
        layers=["cloud_attached"],
        max_nodes=10,
        max_edges=10,
        mode="full",
    )

    assert graph["edges"][0]["verification_state"] == "caller_unverified_v0"
    assert graph["visualization_state"]["materialized"]["verified_relation_count"] == 0


def test_candidate_graph_cartridge_cannot_launder_verified_relation_count(monkeypatch) -> None:
    monkeypatch.setattr(
        materializers,
        "attachment_graph_payload",
        lambda: {
            "nodes": [
                {
                    "id": "graph-cartridge:candidate:a",
                    "label": "Alpha",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                },
                {
                    "id": "graph-cartridge:candidate:b",
                    "label": "Beta",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                },
            ],
            "edges": [
                {
                    "id": "graph-cartridge-edge:candidate:a:b",
                    "source": "graph-cartridge:candidate:a",
                    "target": "graph-cartridge:candidate:b",
                    "relation": "supports",
                    "trust_state": "semantic_candidate_store",
                    "verification_state": "caller_unverified_v0",
                    "independent_source_attestation": False,
                    "authoritative_for_answer": False,
                }
            ],
        },
    )
    monkeypatch.setattr(materializers, "list_active_attachments", lambda: [])

    graph = aggregator.aggregate_brain_graph(
        view="cloud",
        layers=["graph_cartridge"],
        max_nodes=10,
        max_edges=10,
        mode="full",
    )

    assert graph["edges"][0]["verification_state"] == "caller_unverified_v0"
    assert graph["visualization_state"]["materialized"]["verified_relation_count"] == 0
