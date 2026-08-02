from __future__ import annotations

from packages.local_memory_approval.manifest import build_memory_manifest_draft
from packages.local_memory_approval.policy import classify_memory_candidate
from packages.local_memory_approval.review_store import MemoryApprovalReviewStore
from packages.local_memory_write_plan.planner import build_write_plan_from_memory_manifest
from packages.local_memory_sandbox.backup import backup_sandbox_store
from packages.local_memory_sandbox.store import init_sandbox_store, read_collection
from packages.local_memory_sandbox.transaction import apply_write_plan_to_sandbox, validate_transaction


def _write_plan(tmp_path):
    candidate = classify_memory_candidate("ATANOR separates Local Brain and Cloud Brain.", "project_fact")
    store = MemoryApprovalReviewStore(tmp_path / "review")
    session = store.create_memory_review_session([candidate])
    session = store.add_memory_decision(session.session_id, candidate.candidate_id, "approve_for_future_memory_manifest")
    manifest = build_memory_manifest_draft(session)
    return build_write_plan_from_memory_manifest(manifest, session)


def test_apply_write_plan_to_temp_sandbox(tmp_path) -> None:
    plan = _write_plan(tmp_path)
    sandbox = init_sandbox_store(tmp_path / "sandbox")
    backup = backup_sandbox_store(sandbox, tmp_path / "backup")
    tx = apply_write_plan_to_sandbox(plan, sandbox, backup_path=backup.backup_path)
    validation = validate_transaction(tx)

    assert tx.applied is True
    assert tx.real_local_brain_write is False
    assert tx.store_hash_before != tx.store_hash_after
    assert validation["valid"] is True
    assert len(read_collection(sandbox, "project_context")) == 1
