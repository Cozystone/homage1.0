from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_q_cortex_status_and_salience_api_are_local_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    status = client.get("/api/q-cortex/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["architecture"] == "Q-Cortex Optimizer"
    assert payload["real_quantum_hardware_used"] is False
    assert payload["quantum_inspired_only"] is True
    assert payload["external_llm_used"] is False
    assert payload["local_brain_write"] is False

    salience = client.post(
        "/api/q-cortex/salience/optimize",
        json={
            "candidates": [
                {"id": "seed", "kind": "node", "layer": "seed_anchor", "query_relevance": 0.9, "activation": 0.9, "trust": 0.9, "risk": 0.05, "source_id": "seed", "concept_id": "Evidence"},
                {"id": "noise", "kind": "node", "layer": "cloud_attached", "query_relevance": 0.1, "activation": 0.1, "trust": 0.1, "risk": 0.95, "source_id": "noise", "concept_id": "Noise"},
            ],
            "max_nodes": 1,
            "max_edges": 0,
        },
    )
    assert salience.status_code == 200
    salience_payload = salience.json()
    assert salience_payload["selected_count"] <= 1
    assert salience_payload["real_quantum_hardware_used"] is False
    assert salience_payload["external_sllm_used"] is False


def test_q_cortex_proof_api_writes_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    response = client.post("/api/q-cortex/proof")

    assert response.status_code == 200
    payload = response.json()
    assert payload["proof"]["result"] == "PASS"
    assert payload["real_quantum_hardware_used"] is False
    assert payload["local_brain_write"] is False
