from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_base_brain_status_and_build() -> None:
    build_response = client.post("/api/base-brain/build")
    assert build_response.status_code == 200
    assert build_response.json()["built"] is True
    status_response = client.get("/api/base-brain/status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["pack_exists"] is True
    assert payload["semantic_node_count"] >= 30
    assert payload["surface_construction_count"] >= 16


def test_base_brain_answer_schema() -> None:
    response = client.post(
        "/api/base-brain/answer",
        json={"query": "쿠버네티스가 뭐야?", "language": "ko", "audience_level": "beginner", "mode": "default"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert payload["answer_kind"] == "base_brain_zero_user_data"
    assert payload["local_user_brain_used"] is False
    assert payload["external_llm_used"] is False
    assert "Cloud Brain" not in payload["answer"]


def test_base_brain_benchmark_and_proof() -> None:
    benchmark_response = client.post("/api/base-brain/benchmark", json={"limit": 5})
    assert benchmark_response.status_code == 200
    assert benchmark_response.json()["total_prompts"] == 5
    proof_response = client.get("/api/base-brain/proof")
    assert proof_response.status_code == 200
    assert proof_response.json()["status"] == "PASS"
