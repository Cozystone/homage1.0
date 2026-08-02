from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_answer_quality_repair_comparison_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/answer-quality/run-repair-comparison",
        json={"benchmark_set": "core_ko_en_v1", "limit": 8},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_hygiene_after"] >= payload["trace_hygiene_before"]
    assert payload["feedback_auto_promoted"] is False


def test_answer_quality_repair_comparisons_list_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    client.post("/api/answer-quality/run-repair-comparison", json={"limit": 2})
    response = client.get("/api/answer-quality/repair-comparisons")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
