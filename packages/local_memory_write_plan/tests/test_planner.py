from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest


def _session(tmp_path):
    preference = classify_memory_candidate("I prefer natural Korean explanations.", "preference")
    project = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    sensitive = classify_memory_candidate("My email is user@example.com.", "user_text")
    voice_raw = classify_memory_candidate("I like concise voice answers.", "voice_transcript")
    voice_edited = classify_memory_candidate("I prefer brief spoken answers.", "voice_transcript")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([preference, project, sensitive, voice_raw, voice_edited])
    session = store.add_memory_decision(session.session_id, preference.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, project.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, sensitive.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(session.session_id, voice_raw.candidate_id, "approve_for_future_memory_manifest")
    session = store.add_memory_decision(
        session.session_id,
        voice_edited.candidate_id,
        "approve_for_future_memory_manifest",
        edited_summary="User may prefer brief spoken answers.",
    )
    return session, preference, project, sensitive, voice_raw, voice_edited


def test_planner_routes_safe_items_and_skips_raw_sensitive_voice(tmp_path) -> None:
    session, preference, project, sensitive, voice_raw, voice_edited = _session(tmp_path)
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest, session)
    targets = {write.source_memory_candidate_id: write.target_collection for write in plan.writes}
    skipped = {item["candidate_id"]: item["reason"] for item in plan.skipped}

    assert targets[preference.candidate_id] == "preferences"
    assert targets[project.candidate_id] == "project_context"
    assert targets[voice_edited.candidate_id] == "preferences"
    assert skipped[sensitive.candidate_id] == "sensitive_raw_memory_blocked"
    assert skipped[voice_raw.candidate_id] == "voice_raw_transcript_blocked"
    assert all(write.write_allowed is False for write in plan.writes)
    assert plan.apply_enabled is False
    assert plan.local_brain_write is False
    assert plan.local_brain_mutated is False


def test_planner_skips_when_session_context_missing(tmp_path) -> None:
    session, *_ = _session(tmp_path)
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest)

    assert plan.writes == []
    assert {item["reason"] for item in plan.skipped} == {"missing_session_context"}
