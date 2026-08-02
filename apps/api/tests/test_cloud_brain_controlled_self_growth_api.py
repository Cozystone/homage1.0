from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed_research import run_seed_iteration
from seed_research.cloud_fragment_alignment import ensure_deterministic_fixture


def test_controlled_self_growth_api_counts_only_ingested_cloud_fragments(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATANOR_LOCAL_BRAIN_INITIALIZED", raising=False)
    run_seed_iteration("data/seed_research")
    ensure_deterministic_fixture("data/cloud_brain/inbox/pending_fixture.json")
    client = TestClient(app)

    before = client.get("/api/cloud-brain/status")
    assert before.status_code == 200
    before_payload = before.json()
    assert before_payload["cloud_graph_state"]["proof_ingested_fragments"] == 0
    assert before_payload["cloud_graph_state"]["proof_store_nodes"] == 0
    assert before_payload["local_graph_state"]["local_total_nodes"] == 0
    assert before_payload["local_graph_state"]["local_total_relations"] == 0

    run = client.post("/api/cloud-brain/prove-controlled-self-growth")
    assert run.status_code == 200
    proof = run.json()
    assert proof["controlled_self_growth"] is True
    assert proof["alignment_success"] is True
    assert proof["ingestion_success"] is True
    assert proof["query_readback_success"] is True
    assert proof["nodes_added"] >= 3
    assert proof["edges_added"] >= 1
    assert proof["local_brain_state"]["local_total_nodes"] == 0
    assert proof["external_llm_used"] is False
    assert proof["external_sllm_used"] is False
    assert proof["rule_based_answer_engine"] is False
    assert proof["final_answer_generation_claimed"] is False

    after = client.get("/api/cloud-brain/status")
    assert after.status_code == 200
    after_payload = after.json()
    assert after_payload["cloud_graph_state"]["proof_ingested_fragments"] == 1
    assert after_payload["cloud_graph_state"]["proof_store_nodes"] == proof["new_cloud_nodes"]
    assert after_payload["cloud_graph_state"]["proof_store_edges"] == proof["new_cloud_edges"]
    assert after_payload["controlled_self_growth_state"]["last_ingestion_success"] is True
    assert after_payload["controlled_self_growth_state"]["autonomous_broad_crawling"] is False
    assert after_payload["local_graph_state"]["local_total_nodes"] == 0
    assert after_payload["local_graph_state"]["local_total_relations"] == 0


def test_controlled_self_growth_readback_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)

    run = client.post("/api/cloud-brain/prove-controlled-self-growth")
    assert run.status_code == 200
    query = client.get("/api/cloud-brain/fragments/query", params={"q": "Evidence", "limit": 3})
    latest = client.get("/api/cloud-brain/controlled-self-growth-proof")

    assert query.status_code == 200
    assert query.json()["query_readback_success"] is True
    assert query.json()["results"][0]["fragment_id"] == "candidate_seed_alignment_001"
    assert latest.status_code == 200
    assert latest.json()["proof_exists"] is True
    assert latest.json()["controlled_self_growth"] is True
