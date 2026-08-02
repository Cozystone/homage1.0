from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.local_memory_approval import router


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ATANOR_LOCAL_MEMORY_APPROVAL_REVIEW_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_local_memory_approval_status_is_review_only(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = client.get("/api/local-memory-approval/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["apply_enabled"] is False
    assert payload["local_brain_write"] is False
    assert payload["voice_raw_blocked"] is True
    assert payload["safety"]["real_local_brain_write"] is False
    assert payload["safety"]["external_llm_used"] is False


def test_local_memory_approval_session_decision_and_manifest(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    created = client.post(
        "/api/local-memory-approval/session",
        json={"texts": ["ATANOR separates Local Brain and Cloud Brain."], "source_type": "project_fact"},
    )
    assert created.status_code == 200
    session = created.json()
    candidate_id = session["candidates"][0]["candidate_id"]
    assert session["safety"]["memory_apply_enabled"] is False

    decided = client.post(
        f"/api/local-memory-approval/sessions/{session['session_id']}/decision",
        json={"candidate_id": candidate_id, "decision": "approve"},
    )
    assert decided.status_code == 200
    assert decided.json()["decisions"][0]["applied_to_local_brain"] is False

    manifest = client.post(f"/api/local-memory-approval/sessions/{session['session_id']}/manifest-draft")
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["manifest"]["approved_candidate_ids"] == [candidate_id]
    assert payload["manifest"]["ready_for_memory_write"] is False
    assert payload["apply_enabled"] is False
    assert payload["local_brain_write"] is False


def test_local_memory_approval_sensitive_block_stays_metadata_only(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/local-memory-approval/session",
        json={"texts": ["My email is user@example.com."], "source_type": "user_text"},
    ).json()
    candidate_id = created["candidates"][0]["candidate_id"]

    response = client.post(
        f"/api/local-memory-approval/sessions/{created['session_id']}/decision",
        json={"candidate_id": candidate_id, "decision": "sensitive_block"},
    )
    status = client.get("/api/local-memory-approval/status").json()

    assert response.status_code == 200
    assert response.json()["decisions"][0]["decision"] == "sensitive_block"
    assert status["sensitive_block_count"] == 1
    assert status["safety"]["real_local_brain_mutated"] is False
