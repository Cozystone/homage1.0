from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed_research import run_seed_iteration


def test_working_memory_cloud_attachment_api_layers_are_separated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)

    proof = client.post("/api/cloud-brain/prove-controlled-self-growth")
    assert proof.status_code == 200

    inspector = client.get("/api/cloud-brain/source-inspector")
    assert inspector.status_code == 200
    assert inspector.json()["active_source_mode"] == "single_peer_contributor_network"
    assert inspector.json()["contributor_network"]["network_state"] == "active_single_peer"

    created = client.post("/api/working-memory/cloud-attachments/create", json={"query": "GraphRAG evidence"})
    assert created.status_code == 200
    bundle = created.json()["bundle"]
    assert bundle["writes_to_local_brain"] is False
    assert bundle["nodes"][0]["visual_layer"] == "cloud_attached"
    assert bundle["seed_anchor_nodes"]
    assert bundle["seed_anchor_nodes"][0]["visual_layer"] == "seed_anchor"

    attached = client.post("/api/working-memory/cloud-attachments/attach", json={"bundle_id": bundle["bundle_id"]})
    assert attached.status_code == 200
    assert attached.json()["working_memory_overlay"]["cloud_attached_nodes"] == len(bundle["nodes"])
    assert attached.json()["working_memory_overlay"]["seed_anchor_nodes"] == len(bundle["seed_anchor_nodes"])

    graph = client.get("/api/memory/graph", params={"include_cloud_attached": "true", "limit": 40})
    assert graph.status_code == 200
    payload = graph.json()
    assert payload["seed_anchor_nodes"]
    assert payload["counts"]["seed_anchor_nodes"] == len(bundle["seed_anchor_nodes"])
    assert payload["counts"]["cloud_attached_nodes"] == len(bundle["nodes"])
    assert payload["local_brain_empty"] is True
    assert payload["cloud_mirror_excluded_from_local_brain"] is True
    assert payload["counts"]["local_nodes"] == 0
    assert payload["counts"]["local_edges"] == 0
    assert payload["counts"]["local_nodes"] == len(payload["local_nodes"])
    assert payload["working_memory_overlay"]["writes_to_local_brain"] is False

    detached = client.post("/api/working-memory/cloud-attachments/detach", json={"bundle_id": bundle["bundle_id"]})
    assert detached.status_code == 200
    assert detached.json()["working_memory_overlay"]["cloud_attached_nodes"] == 0

    after = client.get("/api/memory/graph", params={"include_cloud_attached": "true", "limit": 40})
    assert after.status_code == 200
    assert after.json()["counts"]["cloud_attached_nodes"] == 0
    assert after.json()["counts"]["seed_anchor_nodes"] == 0
    assert after.json()["counts"]["local_nodes"] == 0
