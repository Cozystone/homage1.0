from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed_research import run_seed_iteration


def test_cloud_fragment_alignment_summary_and_run_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATANOR_LOCAL_BRAIN_INITIALIZED", raising=False)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)

    before = client.get("/api/seed-research/cloud-fragment-alignment")
    assert before.status_code == 200
    assert before.json()["proof_exists"] is False
    assert before.json()["candidate_fragments_checked"] == 0

    run = client.post("/api/seed-research/cloud-fragment-alignment/run")
    assert run.status_code == 200
    payload = run.json()
    assert payload["proof_exists"] is True
    assert payload["candidate_fragments_checked"] == 1
    assert payload["public_fragments_checked"] == 1
    assert payload["fragments_aligned_to_seed"] == 1
    assert payload["concepts_aligned_total"] >= 3
    assert payload["edges_aligned_total"] >= 1
    assert payload["local_brain_state"]["local_brain_initialized"] is False
    assert payload["local_brain_state"]["local_total_nodes"] == 0
    assert payload["local_brain_state"]["local_total_edges"] == 0
    assert payload["external_llm_used"] is False
    assert payload["external_sllm_used"] is False
    assert payload["rule_based_answer_engine"] is False
    assert payload["final_answer_generation_claimed"] is False

    after = client.get("/api/seed-research/cloud-fragment-alignment")
    assert after.status_code == 200
    assert after.json()["proof_exists"] is True
    assert after.json()["matched_fragment_ids"] == ["candidate_seed_alignment_001"]


def test_runtime_trace_includes_cloud_fragment_seed_alignment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATANOR_LOCAL_BRAIN_INITIALIZED", raising=False)
    run_seed_iteration("data/seed_research")
    client = TestClient(app)
    run = client.post("/api/seed-research/cloud-fragment-alignment/run")
    assert run.status_code == 200

    response = client.get("/api/seed-research/runtime-trace", params={"q": "Evidence Claim"})

    assert response.status_code == 200
    trace = response.json()["cloud_alignment_trace"]
    assert trace["cloud_checked"] is True
    assert trace["candidate_fragments_checked"] == 1
    assert trace["public_fragments_checked"] == 1
    assert trace["fragments_aligned_to_seed"] == 1
    assert trace["matched_fragment_ids"] == ["candidate_seed_alignment_001"]
    assert trace["matched_seed_concepts"]
    assert trace["matched_seed_edges"]
    assert trace["writes_to_local_brain"] is False
