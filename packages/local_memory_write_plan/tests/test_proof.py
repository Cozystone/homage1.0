from __future__ import annotations

from packages.local_memory_write_plan.proof import run_proof


def test_run_proof_keeps_local_brain_unchanged(tmp_path) -> None:
    payload = run_proof(tmp_path)

    assert payload["verdict"] == "LOCAL_BRAIN_MEMORY_WRITE_DRY_RUN_PROOF_ONLY"
    assert payload["scenarios"]["approved_preference_creates_write_candidate"] is True
    assert payload["scenarios"]["approved_project_context_creates_write_candidate"] is True
    assert payload["scenarios"]["sensitive_raw_memory_skipped"] is True
    assert payload["scenarios"]["voice_raw_transcript_skipped"] is True
    assert payload["scenarios"]["backup_plan_required_not_created"] is True
    assert payload["scenarios"]["rollback_required_not_executable"] is True
    assert payload["scenarios"]["validator_keeps_apply_disabled"] is True
    assert payload["scenarios"]["local_brain_unchanged"] is True
    assert payload["invariants"]["local_brain_write"] is False
    assert payload["invariants"]["backup_created"] is False
    assert payload["invariants"]["rollback_executed"] is False
    assert any(tmp_path.glob("local_memory_write_plan_proof_*.json"))
