from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from packages.cloud_brain.semantic_growth import ingest_semantic_source


def test_local_cloud_exchange_api_uses_temporary_cloud_chunk(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ingest_semantic_source(
        "Kubernetes manages containerized applications and automates deployment.",
        source_id="api-exchange-proof-001",
        language="en",
        usage_allowed=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/working-memory/local-cloud-exchange",
        json={"query": "Kubernetes가 뭐야?", "pin_context": False, "allow_web": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["local_graph_request"]["state"] == "local_miss"
    assert "cloud_hit" in payload["states"]
    assert payload["cloud_graph_chunk"]["temporary"] is True
    assert payload["cloud_graph_chunk"]["local_write"] is False
    assert payload["working_memory"]["auto_detached"] is True
    assert payload["working_memory"]["overlay_final"]["working_memory_overlay"]["cloud_attached_nodes"] == 0
    assert payload["truth"]["pair_edges_sent"] == 0
    assert payload["truth"]["full_store_scan"] is False


def test_local_cloud_exchange_api_cloud_miss_reports_no_fake_web_results(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/working-memory/local-cloud-exchange",
        json={"query": "zzxqv blorf nosemanticmatch", "allow_web": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "cloud_miss" in payload["states"]
    assert payload["cloud_graph_chunk"] is None
    assert payload["evidence_bundle"]["extraction_status"] == "not_configured"
    assert payload["evidence_bundle"]["snippets"] == []
    assert payload["truth"]["web_results_faked"] is False
    assert payload["truth"]["local_brain_write"] is False
