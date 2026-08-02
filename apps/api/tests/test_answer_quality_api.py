from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_answer_quality_api_status_evaluate_and_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    status = client.get("/api/answer-quality/status")
    assert status.status_code == 200
    assert status.json()["external_llm_judge_used"] is False
    assert status.json()["benchmark_prompts"] >= 50

    score = client.post(
        "/api/answer-quality/evaluate-answer",
        json={
            "query": "GraphRAG가 근거를 어떻게 써?",
            "answer": "Local Brain → Cloud Brain → Working Memory 경로를 사용합니다.",
            "language": "ko",
            "mode": "default",
            "semantic_context": [{"concept": "GraphRAG"}],
        },
    )
    assert score.status_code == 200
    assert "trace_leakage" in score.json()["flags"]

    run = client.post("/api/answer-quality/run", json={"limit": 3})
    assert run.status_code == 200
    payload = run.json()
    assert payload["total_prompts"] == 3
    assert payload["feedback_auto_promoted"] is False


def test_answer_quality_api_proof(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    proof = client.post("/api/answer-quality/proof")

    assert proof.status_code == 200
    assert proof.json()["proof"]["result"] == "PASS"
