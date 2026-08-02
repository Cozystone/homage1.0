from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_surface_repair_answer_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/surface-brain/repair-answer",
        json={
            "answer": "Cloud Brain 문맥을 붙이면 쿠버네티스는 컨테이너 관리 시스템입니다.",
            "mode": "default",
            "trace": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Cloud Brain" not in payload["repaired_answer"]
    assert payload["changed"] is True
    assert payload["moved_to_trace"]


def test_feedback_to_repair_candidates_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/surface-brain/feedback-to-repair-candidates",
        json={
            "run_id": "api-run",
            "feedback_items": [
                {"feedback_id": "api-f1", "type": "repair_pattern", "suggestion": "remove_internal_path_leakage"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"]
    assert payload["auto_promoted"] is False
