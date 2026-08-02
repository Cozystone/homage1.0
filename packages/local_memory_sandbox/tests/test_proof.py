from __future__ import annotations

from packages.local_memory_sandbox.proof import run_proof


def test_run_proof_covers_transaction_and_safety_blocks(tmp_path) -> None:
    payload = run_proof(tmp_path)

    assert payload["verdict"] == "LOCAL_BRAIN_SANDBOX_WRITE_TRANSACTION_PROOF_ONLY"
    assert payload["scenarios"]["initialize_sandbox_store"] is True
    assert payload["scenarios"]["approved_preference_written_to_sandbox"] is True
    assert payload["scenarios"]["approved_project_context_written_to_sandbox"] is True
    assert payload["scenarios"]["backup_created"] is True
    assert payload["scenarios"]["store_hash_changed"] is True
    assert payload["scenarios"]["rollback_executed"] is True
    assert payload["scenarios"]["store_hash_restored"] is True
    assert payload["scenarios"]["sensitive_raw_write_blocked"] is True
    assert payload["scenarios"]["raw_voice_transcript_blocked"] is True
    assert payload["scenarios"]["real_local_brain_path_rejected"] is True
    assert payload["invariants"]["real_local_brain_write"] is False
    assert payload["invariants"]["sandbox_local_brain_write"] is True
    assert payload["invariants"]["sandbox_rollback_verified"] is True
    assert any(tmp_path.glob("local_memory_sandbox_proof_*.json"))
