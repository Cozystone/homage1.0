from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed_research import run_seed_iteration


def test_cortex_status_and_cycle_api_are_local_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    status = client.get("/api/cortex/status")
    assert status.status_code == 200
    assert status.json()["architecture"] == "CORTEX-G2"
    assert status.json()["external_llm_used"] is False
    assert status.json()["external_sllm_used"] is False
    assert status.json()["local_brain_write"] is False

    cycle = client.post(
        "/api/cortex/cycle",
        json={
            "query": "Evidence와 Claim의 차이를 설명해줘.",
            "graph_payload": {
                "seed_anchor_nodes": [
                    {"id": "seed_evidence", "label": "Evidence", "visual_layer": "seed_anchor", "source_scope": "seed"},
                    {"id": "seed_claim", "label": "Claim", "visual_layer": "seed_anchor", "source_scope": "seed"},
                ],
                "cloud_attached_nodes": [
                    {"id": "cloud_source", "label": "Source", "visual_layer": "cloud_attached", "source_scope": "cloud"},
                ],
                "cloud_attached_edges": [
                    {"id": "edge_supports", "source": "seed_evidence", "relation": "supports", "target": "seed_claim", "source_type": "cloud_attached"},
                ],
            },
            "top_k_nodes": 16,
            "top_k_edges": 16,
        },
    )
    assert cycle.status_code == 200
    payload = cycle.json()
    assert payload["summary"]["enabled"] is True
    assert payload["retrieval_trace"]["cortex_g2"]["enabled"] is True
    assert payload["retrieval_trace"]["cortex_g2"]["local_brain_write"] is False
    assert payload["final_answer_generation_claimed"] is False


def test_working_memory_attach_returns_lightweight_overlay_and_cortex_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)

    proof = client.post("/api/cloud-brain/prove-controlled-self-growth")
    assert proof.status_code == 200
    created = client.post("/api/working-memory/cloud-attachments/create", json={"query": "GraphRAG evidence"})
    assert created.status_code == 200
    bundle = created.json()["bundle"]

    attached = client.post("/api/working-memory/cloud-attachments/attach", json={"bundle_id": bundle["bundle_id"]})
    assert attached.status_code == 200
    attached_payload = attached.json()
    assert attached_payload["cortex_g2"]["enabled"] is True
    assert attached_payload["cortex_g2"]["local_brain_write"] is False
    assert attached_payload["retrieval_trace"]["cortex_g2"]["self_generated_truth_saved"] is False

    listed = client.get("/api/working-memory/cloud-attachments")
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload["working_memory_overlay"]["active"] is True
    assert listed_payload["working_memory_overlay"]["cloud_attached_nodes"] == len(bundle["nodes"])
    assert listed_payload["working_memory_overlay"]["seed_anchor_nodes"] == len(bundle["seed_anchor_nodes"])
    assert listed_payload["working_memory_overlay"]["writes_to_local_brain"] is False
