from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_cloud_learning_status_separates_running_from_learning(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    response = client.get("/api/cloud-brain/learning/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["learning_status_endpoint"] is True
    assert "daemon_running" in payload
    assert "actually_learning" in payload
    assert payload["mock_growth"] is False
    assert payload["local_brain_write"] is False
    assert payload["pair_edges_sent"] == 0


def test_cloud_learning_run_once_rejects_unbound_caller_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidate_store = tmp_path / "candidate_store"
    candidate_store.mkdir()
    monkeypatch.setenv("ATANOR_CANDIDATE_STORE_PATH", str(candidate_store))
    response = client.post(
        "/api/cloud-brain/learning/run-once",
        json={
            "payloads": [
                {
                    "source_type": "manual_public_sentence",
                    "source_id": "manual:api-learning:1",
                    "text": "Kubernetes manages containerized applications across distributed clusters.",
                    "language": "en",
                    "license_hint": "CC BY-SA 4.0",
                    "source_url_or_path": "manual://public/api-learning/1",
                }
            ],
        },
    )
    assert response.status_code == 400
    assert "independently bound source observation" in response.json()["detail"]
    assert not (candidate_store / "manifest.json").exists()


def test_cloud_surface_graph_and_identity_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    surface = client.get("/api/cloud-brain/surface-graph/status")
    identity = client.get("/api/cloud-brain/identity")
    assert surface.status_code == 200
    assert identity.status_code == 200
    assert surface.json()["cgsr_consumes_surface_projection"] is True
    assert surface.json()["production_store_mutated"] is False
    assert identity.json()["promotion_default"] == "manual_review_required"
    assert identity.json()["mock_growth_allowed"] is False
