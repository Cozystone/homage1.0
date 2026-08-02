from __future__ import annotations

import json
from pathlib import Path
import hashlib

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _candidate_store(tmp_path: Path) -> Path:
    store = tmp_path / "candidate_api_store"
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
    (store / "concepts.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"concept_id": "candidate-api-a", "canonical_name": "Candidate API A", "language": "en"}),
                json.dumps({"concept_id": "candidate-api-b", "canonical_name": "Candidate API B", "language": "en"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (store / "relations.jsonl").write_text(
        json.dumps(
            {
                "relation_id": "candidate-api-edge-1",
                "source_concept_id": "candidate-api-a",
                "target_concept_id": "candidate-api-b",
                "relation": "CANDIDATE_RELATION",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (store / "evidence.jsonl").write_text(json.dumps({"source_id": "fixture-source"}) + "\n", encoding="utf-8")
    (store / "case_frames.jsonl").write_text(json.dumps({"frame_id": "candidate-frame-1"}) + "\n", encoding="utf-8")
    return store


def test_candidate_status_endpoint_reports_candidate_counts(tmp_path: Path) -> None:
    store = _candidate_store(tmp_path)
    response = client.get("/api/cloud-brain/candidate/status", params={"candidate_store_path": str(store)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_available"] is True
    assert payload["candidate_concepts"] > 0
    assert payload["candidate_relations"] > 0
    assert payload["candidate_evidence"] > 0
    assert payload["candidate_case_frames"] > 0
    assert payload["candidate_is_verified"] is False
    assert payload["production_store_mutated"] is False
    assert payload["pair_edges_sent"] == 0


def test_candidate_graph_endpoint_is_opt_in_and_candidate_marked(tmp_path: Path) -> None:
    store = _candidate_store(tmp_path)
    response = client.get(
        "/api/cloud-brain/candidate/graph",
        params={"candidate_store_path": str(store), "max_nodes": 25, "max_edges": 50},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["candidate_graph_available"] is True
    assert payload["metadata"]["candidate_is_verified"] is False
    assert payload["metadata"]["full_store_scan"] is False
    assert payload["metadata"]["pair_edges_sent"] == 0
    assert payload["nodes"]
    assert all(node["candidate"] is True for node in payload["nodes"])
    assert all(node["source_store"] == "candidate" for node in payload["nodes"])


def test_default_brain_graph_does_not_include_candidate_overlay(tmp_path: Path) -> None:
    _candidate_store(tmp_path)
    response = client.get("/api/brain/graph", params={"view": "cloud", "mode": "fast", "max_nodes": 50, "max_edges": 50})

    assert response.status_code == 200
    payload = response.json()
    metadata = payload.get("metadata") or {}
    assert metadata.get("candidate_available") is not True
    assert metadata.get("candidate_is_verified") is not True


def test_run_capped_rejects_unbound_capacity_probe_payload(tmp_path: Path) -> None:
    text = "Public evidence supports candidate learning with source capacity planning."
    response = client.post(
        "/api/cloud-brain/learning/run-capped",
        json={
            "execute": True,
            "dry_run": False,
            "max_payloads": 1,
            "max_seconds": 60,
            "min_ram_free_gb": 0,
            "min_disk_free_gb": 0,
            "max_cpu_percent": None,
            "max_candidate_files": None,
            "target_candidate_store": str(tmp_path / "candidate"),
            "target_payloads_per_second": 5,
            "target_duration_seconds": 21600,
            "pacing_mode": "sleep_between_batches",
            "payloads": [
                {
                    "payload_id": "api-rate-test-1",
                    "source_type": "local_public_corpus_shard",
                    "source_id": "fixture:api-rate-test:1",
                    "source_url_or_path": "file://fixture/public.jsonl#L1",
                    "provenance_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "license_hint": "CC BY-SA 4.0 test fixture",
                    "language": "en",
                    "text": text,
                    "is_private": False,
                    "is_generated": False,
                    "is_eval_row": False,
                    "target_store": "verified_store_v0_candidate",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert not (tmp_path / "candidate").exists()
