from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.backup import create_backup_plan
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest
from packages.local_memory_write_plan.rollback import create_rollback_plan
from packages.local_memory_write_plan.validator import validate_write_plan


def test_validator_accepts_non_applying_dry_run(tmp_path) -> None:
    candidate = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest, session)
    backup = create_backup_plan(source_manifest_id=manifest.manifest_id)
    rollback = create_rollback_plan(backup)
    validation = validate_write_plan(manifest, plan, backup, rollback, session)

    assert validation.valid is True
    assert validation.apply_enabled is False
    assert validation.local_brain_write is False
    assert validation.required_gates["backup_plan_required"] is True
    assert validation.required_gates["rollback_plan_required"] is True
    assert validation.required_gates["backup_created"] is False


def test_validator_warns_without_session_context(tmp_path) -> None:
    candidate = classify_memory_candidate("I prefer short answers.", "preference")
    store = MemoryApprovalReviewStore(tmp_path)
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest)
    backup = create_backup_plan(source_manifest_id=manifest.manifest_id)
    rollback = create_rollback_plan(backup)
    validation = validate_write_plan(manifest, plan, backup, rollback)

    assert validation.valid is True
    assert "session_context_missing_for_candidate_policy_validation" in validation.warnings
