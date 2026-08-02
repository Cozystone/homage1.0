from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest
from packages.local_memory_sandbox.backup import backup_sandbox_store
from packages.local_memory_sandbox.rollback import rollback_sandbox_store
from packages.local_memory_sandbox.store import compute_store_hash, init_sandbox_store
from packages.local_memory_sandbox.transaction import apply_write_plan_to_sandbox


def test_rollback_restores_pre_write_hash(tmp_path) -> None:
    candidate = classify_memory_candidate("I prefer concise answers.", "preference")
    store = MemoryApprovalReviewStore(tmp_path / "review")
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    plan = build_write_plan_from_memory_manifest(manifest, session)
    sandbox = init_sandbox_store(tmp_path / "sandbox")
    before = compute_store_hash(sandbox)
    backup = backup_sandbox_store(sandbox, tmp_path / "backup")
    tx = apply_write_plan_to_sandbox(plan, sandbox, backup_path=backup.backup_path)
    result = rollback_sandbox_store(tx)

    assert result.rollback_executed is True
    assert result.sandbox_rollback_verified is True
    assert result.store_hash_after_rollback == before
    assert compute_store_hash(sandbox) == before
