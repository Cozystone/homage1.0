from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_semantic_cloud_growth_api_ingest_status_graph_and_attach(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sample = "쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다."
    ingest = client.post(
        "/api/cloud-brain/semantic/ingest",
        json={"text": sample, "source_id": "api-semantic-growth-test", "language": "ko", "usage_allowed": False},
    )
    assert ingest.status_code == 200
    assert ingest.json()["honesty"]["local_brain_write"] is False

    status = client.get("/api/cloud-brain/semantic/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["concepts"] > 0
    assert status_payload["old_mirror_snapshot_used_as_live_cloud"] is False

    graph = client.get("/api/cloud-brain/semantic/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    assert graph.json()["old_mirror_snapshot_used"] is False

    attach = client.post("/api/cloud-brain/semantic/attach", json={"query": "쿠버네티스가 뭐야?", "limit": 8})
    assert attach.status_code == 200
    assert attach.json()["temporary"] is True
    assert attach.json()["local_brain_write"] is False


def test_semantic_cloud_accelerate_api_uses_real_batch_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accelerate = client.post("/api/cloud-brain/semantic/accelerate", json={"batch_size": 1000})
    assert accelerate.status_code == 200
    payload = accelerate.json()
    assert payload["batch_size_applied"] == 1000
    assert payload["fake_counter"] is False
    assert payload["honesty"]["local_brain_write"] is False
    assert payload["honesty"]["external_llm_used"] is False
    assert payload["concepts_created"] >= 1000
    assert payload["relations_created"] >= 1000
    assert payload["max_safe_batch_size"] >= 1000
