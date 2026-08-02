from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from packages.construction_bank.models import get_default_construction_bank


def test_construction_promotion_manifest_api_is_proof_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bank = get_default_construction_bank()
    bank.candidates.clear()
    client = TestClient(app)

    extracted = client.post(
        "/api/construction-bank/extract",
        json={
            "sources": [
                {
                    "source_type": "operator_example",
                    "language": "ko",
                    "route_type": "voice_status",
                    "act": "voice_question",
                    "text": "Fish 음성은 런타임 연결이 확인될 때만 재생하고, 실패하면 텍스트로 이어갑니다.",
                    "source_refs": ["api-test"],
                    "grounding_quality": "high",
                }
            ],
            "store": True,
        },
    )
    assert extracted.status_code == 200
    candidate_id = extracted.json()["candidates"][0]["candidate_id"]
    bank.mark_status(candidate_id, "reviewed")

    draft = client.post(
        "/api/construction-bank/promotion/manifest/draft",
        json={"candidate_ids": [candidate_id], "created_by": "api-test"},
    )
    assert draft.status_code == 200
    manifest = draft.json()["manifest"]
    assert manifest["candidate_ids"] == [candidate_id]
    assert manifest["production_activation"] is False
    assert manifest["production_construction_activation"] is False
    assert manifest["signed_manifest_required"] is True
    assert manifest["rollback_required"] is True

    evaluated = client.post(
        "/api/construction-bank/promotion/manifest/evaluate",
        json={"manifest_id": manifest["manifest_id"]},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["production_activation"] is False
    assert evaluated.json()["external_llm"] is False

    signed = client.post(
        "/api/construction-bank/promotion/manifest/sign-preview",
        json={"manifest_id": manifest["manifest_id"], "operator_signature": "preview"},
    )
    assert signed.status_code == 200
    assert signed.json()["manifest"]["status"] == "signed"
    assert signed.json()["manifest"]["production_activation"] is False

    rollback = client.post(
        "/api/construction-bank/promotion/rollback/draft",
        json={"candidate_ids": [candidate_id], "route_scopes": ["voice_status"]},
    )
    assert rollback.status_code == 200
    assert rollback.json()["rollback"]["executable"] is False
    assert rollback.json()["production_store_mutated"] is False

