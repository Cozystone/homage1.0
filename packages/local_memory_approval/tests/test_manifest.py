from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft, proof_sign_manifest, validate_memory_manifest
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore


def test_manifest_draft_is_stable_and_non_applying(tmp_path) -> None:
    candidate = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")

    first = build_memory_manifest_draft(session, created_at="2026-01-01T00:00:00Z")
    second = build_memory_manifest_draft(session, created_at="2026-12-31T00:00:00Z")
    validation = validate_memory_manifest(session, first)
    signed = proof_sign_manifest(first, "proof-reviewer")

    assert first.canonical_hash == second.canonical_hash
    assert validation["valid"] is True
    assert first.ready_for_memory_write is False
    assert first.apply_enabled is False
    assert first.local_brain_write is False
    assert signed.signature == f"proof-memory-signature:{first.canonical_hash}"
    assert signed.ready_for_memory_write is False


def test_sensitive_and_voice_require_edited_summary(tmp_path) -> None:
    sensitive = classify_memory_candidate("My email is user@example.com.", "user_text")
    voice = classify_memory_candidate("I like concise answers.", "voice_transcript")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([sensitive, voice])
    session = store.add_memory_decision(session.session_id, sensitive.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, voice.candidate_id, "approve_for_future_memory_manifest")

    manifest = build_memory_manifest_draft(session)
    errors = validate_memory_manifest(session, manifest)["errors"]

    assert any("sensitive_requires_edited_summary" in error for error in errors)
    assert any("voice_transcript_requires_edited_summary" in error for error in errors)


def test_sensitive_with_edited_summary_can_enter_draft(tmp_path) -> None:
    sensitive = classify_memory_candidate("My email is user@example.com.", "user_text")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([sensitive])
    session = store.add_memory_decision(
        session.session_id,
        sensitive.candidate_id,
        "approve_for_future_memory_manifest",
        edited_summary="User provided private contact details; do not store raw value.",
    )

    manifest = build_memory_manifest_draft(session)
    validation = validate_memory_manifest(session, manifest)

    assert validation["valid"] is True
    assert "user@example.com" not in manifest.approved_memory_summaries[sensitive.candidate_id]
