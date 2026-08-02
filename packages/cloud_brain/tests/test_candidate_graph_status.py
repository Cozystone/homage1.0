from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.candidate_read_model import candidate_cloud_graph, candidate_cloud_status


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _build_candidate_store(tmp_path: Path) -> Path:
    store = tmp_path / "candidate_store"
    store.mkdir(parents=True, exist_ok=True)
    (store / "manifest.json").write_text(
        json.dumps(
            {
                "store_id": "cloud_brain_verified_store_v0_candidate",
                "counts": {"concepts": 2, "relations": 1, "evidence": 1, "case_frames": 1},
                "honesty": {"production_store_mutated": False, "local_brain_write": False, "mock_growth": False},
            }
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        store / "concepts.jsonl",
        [
            {"concept_id": "candidate-a", "canonical_name": "Candidate A", "language": "en"},
            {"concept_id": "candidate-b", "canonical_name": "Candidate B", "language": "en"},
        ],
    )
    _write_jsonl(
        store / "relations.jsonl",
        [
            {
                "relation_id": "candidate-edge-1",
                "source_concept_id": "candidate-a",
                "target_concept_id": "candidate-b",
                "relation": "CANDIDATE_RELATION",
                "language": "en",
            }
        ],
    )
    _write_jsonl(store / "evidence.jsonl", [{"source_id": "fixture-source"}])
    _write_jsonl(store / "case_frames.jsonl", [{"frame_id": "candidate-frame-1", "canonical_form": "TOPIC OBJ PREDICATE:test"}])
    return store


def test_candidate_status_reads_candidate_store_without_production_claims(tmp_path: Path) -> None:
    store = _build_candidate_store(tmp_path)
    status = candidate_cloud_status(store)

    assert status["candidate_available"] is True
    assert status["candidate_concepts"] > 0
    assert status["candidate_relations"] > 0
    assert status["candidate_evidence"] > 0
    assert status["candidate_case_frames"] > 0
    assert status["surface_candidates"] == status["candidate_case_frames"]
    assert status["cgsr_frames"] == status["candidate_case_frames"]
    assert status["rhfc_candidates"] == status["candidate_case_frames"]
    assert status["candidate_is_verified"] is False
    assert status["production_store_mutated"] is False
    assert status["local_brain_write"] is False
    assert status["pair_edges_sent"] == 0


def test_candidate_graph_marks_nodes_and_edges_as_candidate(tmp_path: Path) -> None:
    store = _build_candidate_store(tmp_path)
    graph = candidate_cloud_graph(store, max_nodes=50, max_edges=100)

    assert graph["metadata"]["candidate_graph_available"] is True
    assert graph["metadata"]["full_store_scan"] is False
    assert graph["metadata"]["index_rebuild_during_request"] is False
    assert graph["metadata"]["pair_edges_sent"] == 0
    assert graph["nodes"]
    assert all(node["candidate"] is True for node in graph["nodes"])
    assert all(node["source_store"] == "candidate" for node in graph["nodes"])
    assert all(node["is_verified_production"] is False for node in graph["nodes"])
    assert all(edge["candidate"] is True for edge in graph["edges"])
    assert all(edge["source_store"] == "candidate" for edge in graph["edges"])
