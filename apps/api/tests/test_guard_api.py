from fastapi.testclient import TestClient

from app.main import app


def test_guard_api_exposes_token_overlap_as_non_authoritative_diagnostic() -> None:
    client = TestClient(app)
    evidence = {"evidence_docs": [{"snippet": "Berlin is the capital of Germany."}]}

    contradictory = client.post(
        "/api/guard/check",
        json={"draft_answer": "Paris is the capital of Germany.", "evidence_bundle": evidence},
    )
    legitimate = client.post(
        "/api/guard/check",
        json={"draft_answer": "Berlin is the capital of Germany.", "evidence_bundle": evidence},
    )

    assert contradictory.status_code == legitimate.status_code == 200
    contradictory_result = contradictory.json()["result"]
    legitimate_result = legitimate.json()["result"]
    for result in (contradictory_result, legitimate_result):
        assert result["support_authority"] == "none"
        assert result["basis"] == "unverified_token_overlap"
        assert result["claims"][0]["support"] == "lexical_match"
        assert result["claims"][0]["support_authority"] == "none"
        assert result["claims"][0]["basis"] == "unverified_token_overlap"
    assert contradictory_result["overall_guard_score"] == legitimate_result["overall_guard_score"] == 100
