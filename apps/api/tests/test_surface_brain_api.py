from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_surface_brain_api_extract_plan_realize(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    status = client.get("/api/surface-brain/status")
    assert status.status_code == 200
    assert status.json()["external_llm_used"] is False

    extracted = client.post(
        "/api/surface-brain/extract",
        json={"text": "쉽게 말하면, 쿠버네티스는 운영 관리자에 가깝습니다."},
    )
    assert extracted.status_code == 200
    assert extracted.json()["surface_projection"]["source_hash"] == extracted.json()["source_hash"]
    assert extracted.json()["stored_raw_text"] is False

    planned = client.post(
        "/api/speech/plan",
        json={"query": "쿠버네티스가 뭐야?", "semantic_context": {"concepts": ["Kubernetes", "containers"]}, "language": "ko"},
    )
    assert planned.status_code == 200
    assert planned.json()["local_brain_write"] is False

    realized = client.post(
        "/api/speech/realize",
        json={"query": "쿠버네티스가 뭐야?", "surface_plan": planned.json(), "semantic_context": {"concepts": ["Kubernetes", "containers"]}},
    )
    assert realized.status_code == 200
    assert realized.json()["honesty"]["external_sllm_used"] is False

