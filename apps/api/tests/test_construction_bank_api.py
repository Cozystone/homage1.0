from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_construction_bank_api_extract_retrieve_compare_and_export(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    extract = client.post(
        "/api/construction-bank/extract",
        json={
            "sources": [
                {
                    "source_type": "operator_example",
                    "language": "ko",
                    "route_type": "voice_status",
                    "act": "voice_question",
                    "text": "Fish 음성은 선택 기능이고, 준비되지 않으면 텍스트로 이어갑니다.",
                    "source_refs": ["test"],
                    "grounding_quality": "medium",
                }
            ],
            "store": True,
        },
    )
    assert extract.status_code == 200
    payload = extract.json()
    assert payload["external_llm"] is False
    assert payload["construction_auto_promoted"] is False
    assert payload["production_construction_activation"] is False
    candidate_id = payload["candidates"][0]["candidate_id"]

    retrieve = client.post(
        "/api/construction-bank/retrieve",
        json={"route_type": "voice_status", "language": "ko", "act": "voice_question", "audience": "lab"},
    )
    assert retrieve.status_code == 200
    retrieve_payload = retrieve.json()
    assert retrieve_payload["retrieved_self_grown_construction"] is True
    assert retrieve_payload["self_grown_construction_used"] is False
    assert "candidate_preview_only" in retrieve_payload["rejection_reasons"]
    assert retrieve_payload["production_active"] is False

    compare = client.post("/api/construction-bank/compare", json={"prompt": "Fish2 소리 상태 알려줘", "mode": "lab"})
    assert compare.status_code == 200
    compare_payload = compare.json()
    assert compare_payload["route"]["route_type"] == "voice_status"
    assert compare_payload["hand_authored_answer"]
    assert compare_payload["metadata"]["production_active"] is False
    assert compare_payload["metadata"]["production_construction_activation"] is False

    exported = client.post("/api/construction-bank/export-review-item", json={"candidate_id": candidate_id})
    assert exported.status_code == 200
    body = exported.json()
    assert body["review_item"]["item_type"] == "construction_candidate"
    assert body["mutation_performed"] is False

    status = client.get("/api/construction-bank/status")
    assert status.status_code == 200
    assert status.json()["production_active_count"] == 0
