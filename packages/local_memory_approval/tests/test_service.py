from __future__ import annotations

from packages.local_memory_approval.service import (
    add_decision,
    build_manifest_draft,
    create_session_from_texts,
    get_session,
    get_status,
    list_sessions,
)


def test_service_creates_review_only_session(tmp_path) -> None:
    session = create_session_from_texts(
        ["I prefer short answers.", "My email is user@example.com."],
        "user_text",
        root=tmp_path,
    )
    status = get_status(root=tmp_path)

    assert session["local_brain_mutated"] is False
    assert session["production_store_mutated"] is False
    assert session["safety"]["real_local_brain_write"] is False
    assert session["safety"]["memory_apply_enabled"] is False
    assert status["sessions_count"] == 1
    assert status["pending_review_count"] == 2
    assert status["voice_raw_blocked"] is True


def test_service_records_decisions_and_manifest_preview(tmp_path) -> None:
    session = create_session_from_texts(["ATANOR separates Local Brain and Cloud Brain."], "project_fact", root=tmp_path)
    candidate_id = session["candidates"][0]["candidate_id"]

    updated = add_decision(session["session_id"], candidate_id, "approve", root=tmp_path)
    manifest = build_manifest_draft(session["session_id"], root=tmp_path)
    sessions = list_sessions(root=tmp_path)

    assert updated["decisions"][0]["applied_to_local_brain"] is False
    assert manifest["manifest"]["approved_candidate_ids"] == [candidate_id]
    assert manifest["manifest"]["ready_for_memory_write"] is False
    assert manifest["apply_enabled"] is False
    assert sessions[0]["decision_counts"] == {"approve_for_future_memory_manifest": 1}


def test_service_supports_edit_and_sensitive_block_without_apply(tmp_path) -> None:
    session = create_session_from_texts(["Call me at +1 555 010 1000."], "user_text", root=tmp_path)
    candidate_id = session["candidates"][0]["candidate_id"]

    add_decision(
        session["session_id"],
        candidate_id,
        "sensitive_block",
        edited_summary="User shared contact information; block raw storage.",
        root=tmp_path,
    )
    loaded = get_session(session["session_id"], root=tmp_path)
    manifest = build_manifest_draft(session["session_id"], root=tmp_path)
    status = get_status(root=tmp_path)

    assert loaded["decisions"][0]["decision"] == "sensitive_block"
    assert manifest["manifest"]["rejected_candidate_ids"] == [candidate_id]
    assert status["sensitive_block_count"] == 1
    assert status["safety"]["real_local_brain_mutated"] is False
