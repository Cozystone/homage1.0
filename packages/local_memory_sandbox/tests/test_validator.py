from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest
from packages.local_memory_sandbox.backup import backup_sandbox_store
from packages.local_memory_sandbox.rollback import rollback_sandbox_store
from packages.local_memory_sandbox.store import init_sandbox_store
from packages.local_memory_sandbox.transaction import apply_write_plan_to_sandbox
from packages.local_memory_sandbox.validator import validate_sandbox_cycle


def test_validate_full_sandbox_cycle(tmp_path) -> None:
    candidate = classify_memory_candidate("I prefer concise answers.", "preference")
    review = MemoryApprovalReviewStore(tmp_path / "review")
    session = review.create_memory_review_session([candidate])
    session = review.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest, session)
    sandbox = init_sandbox_store(tmp_path / "sandbox")
    backup = backup_sandbox_store(sandbox, tmp_path / "backup")
    tx = apply_write_plan_to_sandbox(plan, sandbox, backup_path=backup.backup_path)
    rollback = rollback_sandbox_store(tx)
    validation = validate_sandbox_cycle(backup, tx, rollback)

    assert validation["valid"] is True
    assert validation["real_local_brain_write"] is False
    assert validation["sandbox_local_brain_write"] is True
    assert validation["sandbox_rollback_verified"] is True
