from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.cloud_brain.chunk_index import build_chunk_index
from packages.cloud_brain.planetary_topology import planetize_graph_sample
from packages.cloud_brain.read_model import build_cloud_read_model, load_cloud_read_model_status, load_fast_graph_sample
from packages.cloud_brain.semantic_store import SemanticCloudStore


def _write_store(root: Path) -> None:
    store = root / "store"
    store.mkdir(parents=True, exist_ok=True)
    concepts = {
        "concept:kubernetes": {
            "concept_id": "concept:kubernetes",
            "canonical_name": "Kubernetes",
            "aliases": ["쿠버네티스"],
            "trust": 0.8,
            "confidence": 0.9,
            "seen_count": 2,
            "source_hashes": ["source-a"],
        },
        "concept:container": {
            "concept_id": "concept:container",
            "canonical_name": "Container",
            "aliases": ["컨테이너"],
            "trust": 0.8,
            "confidence": 0.9,
            "seen_count": 2,
            "source_hashes": ["source-a"],
        },
    }
    relations = {
        "rel:kubernetes:manages:container": {
            "relation_id": "rel:kubernetes:manages:container",
            "source_concept_id": "concept:kubernetes",
            "relation": "manages",
            "target_concept_id": "concept:container",
            "weight": 0.72,
            "confidence": 0.82,
            "seen_count": 2,
            "source_hashes": ["source-a"],
        }
    }
    (store / "semantic_concepts.json").write_text(json.dumps(concepts), encoding="utf-8")
    (store / "semantic_relations.json").write_text(json.dumps(relations), encoding="utf-8")
    (store / "semantic_evidence.jsonl").write_text(json.dumps({"source_hash": "source-a"}) + "\n", encoding="utf-8")


def test_build_and_read_cloud_read_model(tmp_path: Path) -> None:
    _write_store(tmp_path)

    result = build_cloud_read_model(tmp_path, limit_nodes=10, limit_edges=10)
    assert result["rebuilt"] is True
    assert (tmp_path / "index" / "fast_graph_sample.json").exists()
    assert result["status"]["concepts"] == 2
    assert result["status"]["relations"] == 1
    assert result["sample"]["nodes"]
    assert result["sample"]["edges"]

    status = load_cloud_read_model_status(tmp_path)
    sample = load_fast_graph_sample(tmp_path, limit_nodes=5, limit_edges=5)
    assert status["performance"]["cache_hit"] is True
    assert status["performance"]["full_store_scan"] is False
    assert sample["performance"]["cache_hit"] is True
    assert sample["performance"]["index_rebuild_during_request"] is False
    chunks = sample["counts"]["chunks"]
    assert chunks["render_mode"] == "spherical_lod_shell"
    assert chunks["compression_used"] is False
    assert chunks["semantic_aggregate_nodes_used"] is False
    assert chunks["all_nodes_rendered"] is False
    assert chunks["logical_node_count"] == 2
    assert chunks["stored_relation_count"] == 1
    assert chunks["density_chunks"]
    assert all(chunk["type"] == "density_chunk" for chunk in chunks["density_chunks"])
    assert all(chunk["is_semantic_node"] is False for chunk in chunks["density_chunks"])
    assert sample["counts"]["spherical_layout"]["layout_version"] == "spherical_onion_v2"
    assert sample["counts"]["spherical_layout"]["density_chunks_are_semantic_nodes"] is False
    assert all(node.get("spherical_layout_version") == "spherical_onion_v2" for node in sample["nodes"])


def test_fast_read_path_does_not_load_full_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_store(tmp_path)
    build_cloud_read_model(tmp_path, limit_nodes=10, limit_edges=10)

    def fail_full_load(*args: object, **kwargs: object) -> object:
        raise AssertionError("fast read path must not load full semantic store")

    monkeypatch.setattr(SemanticCloudStore, "load_concepts", fail_full_load)
    monkeypatch.setattr(SemanticCloudStore, "load_relations", fail_full_load)
    status = load_cloud_read_model_status(tmp_path)
    sample = load_fast_graph_sample(tmp_path, limit_nodes=5, limit_edges=5)

    assert status["concepts"] == 2
    assert sample["nodes"]
    assert sample["performance"]["full_store_scan"] is False


def test_fast_status_does_not_scan_growth_shard_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_store(tmp_path)
    build_cloud_read_model(tmp_path, limit_nodes=10, limit_edges=10)

    from packages.cloud_brain import status_cache

    def fail_shard_scan(*args: object, **kwargs: object) -> object:
        raise AssertionError("fast status must not scan every growth shard")

    monkeypatch.setattr(status_cache, "shards_signature", fail_shard_scan)
    status = load_cloud_read_model_status(tmp_path)
    sample = load_fast_graph_sample(tmp_path, limit_nodes=5, limit_edges=5)

    assert status["performance"]["full_store_scan"] is False
    assert sample["performance"]["full_store_scan"] is False
    assert sample["performance"]["index_rebuild_during_request"] is False


def test_large_logical_graph_gets_dense_render_only_shell_chunks() -> None:
    nodes = [
        {
            "id": f"concept:{index}",
            "metadata": {"domain_cluster_id": f"domain:{index % 8}"},
        }
        for index in range(32)
    ]
    edges = [
        {
            "source": f"concept:{index}",
            "target": f"concept:{(index + 8) % 32}",
        }
        for index in range(32)
    ]

    chunks = build_chunk_index(
        nodes,
        edges,
        logical_node_count=1_000_000,
        logical_relation_count=2_000_000,
        max_shell_chunks=128,
    )

    density_chunks = chunks["density_chunks"]
    assert chunks["visible_scale_chunk_count"] == 128
    assert len(density_chunks) == 128
    assert chunks["materialized_node_count"] == 32
    assert chunks["all_nodes_rendered"] is False
    assert chunks["compression_used"] is False
    assert chunks["semantic_aggregate_nodes_used"] is False
    assert sum(int(chunk["represents_node_count"]) for chunk in density_chunks) == 1_000_000
    assert sum(int(chunk["represents_relation_count"]) for chunk in density_chunks) == 2_000_000
    assert all(chunk["is_semantic_node"] is False for chunk in density_chunks)
    assert all(chunk["semantic_aggregate_node"] is False for chunk in density_chunks)
    assert all(chunk["is_materialization_container"] is True for chunk in density_chunks)
    assert all(chunk["loaded"] is False for chunk in density_chunks)
    assert all(isinstance(chunk.get("x"), float) for chunk in density_chunks)
    assert all(isinstance(chunk.get("y"), float) for chunk in density_chunks)
    assert all(isinstance(chunk.get("z"), float) for chunk in density_chunks)
    assert len({chunk["onion_layer"] for chunk in density_chunks}) >= 3
    metrics = chunks["geometry_metrics"]
    assert metrics["spherical_uniformity_score"] > 0.55
    assert metrics["planar_collapse_score"] < 0.45


def test_planetary_materialized_nodes_keep_deterministic_3d_spherical_spacing() -> None:
    nodes = [
        {
            "id": f"concept:spherical:{index:03d}",
            "label": f"Spherical Concept {index}",
            "metadata": {"planetary_domain": f"domain_{index % 7}"},
        }
        for index in range(96)
    ]
    edges = [
        {
            "id": f"rel:{index:03d}",
            "source": f"concept:spherical:{index:03d}",
            "target": f"concept:spherical:{(index * 17 + 11) % 96:03d}",
            "relation": "related_to",
        }
        for index in range(96)
    ]

    first = planetize_graph_sample(nodes, edges)
    second = planetize_graph_sample(nodes, edges)
    first_positions = {
        node["id"]: (node["x"], node["y"], node["z"])
        for node in first["nodes"]
        if node.get("metadata", {}).get("is_semantic_node") is True
    }
    second_positions = {
        node["id"]: (node["x"], node["y"], node["z"])
        for node in second["nodes"]
        if node.get("metadata", {}).get("is_semantic_node") is True
    }

    assert first_positions == second_positions
    assert len(first_positions) == 96
    xs = [position[0] for position in first_positions.values()]
    ys = [position[1] for position in first_positions.values()]
    zs = [position[2] for position in first_positions.values()]
    spans = [max(axis) - min(axis) for axis in (xs, ys, zs)]
    assert min(spans) > 8.0
    assert min(spans) / max(spans) > 0.55
    assert all(first["nodes"][index]["id"] == nodes[index]["id"] for index in range(96))
    assert all(node.get("metadata", {}).get("is_materialization_container") is False for node in first["nodes"][:96])


def test_missing_read_model_returns_fast_unavailable_view(tmp_path: Path) -> None:
    status = load_cloud_read_model_status(tmp_path)
    sample = load_fast_graph_sample(tmp_path, limit_nodes=5, limit_edges=5)

    assert status["read_model_available"] is False
    assert status["performance"]["full_store_scan"] is False
    assert sample["nodes"] == []
    assert sample["edges"] == []
    assert sample["graph_unavailable_reason"] == "cloud_graph_sample_index_missing"
    assert sample["performance"]["index_rebuild_during_request"] is False
