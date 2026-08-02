from __future__ import annotations

from packages.local_memory_approval.proof import run_proof


def test_run_proof_keeps_all_memory_writes_disabled(tmp_path) -> None:
    payload = run_proof(tmp_path)

    assert payload["verdict"] == "LOCAL_BRAIN_MEMORY_APPROVAL_GATE_PROOF_ONLY"
    assert payload["scenarios"]["preference"]["memory_type"] == "preference"
    assert payload["scenarios"]["project_context"]["manifest_draft_possible"] is True
    assert payload["scenarios"]["sensitive"]["raw_write_allowed"] is False
    assert payload["scenarios"]["voice"]["raw_transcript_direct_write"] is False
    assert payload["scenarios"]["approval_session"]["local_brain_mutated"] is False
    assert payload["scenarios"]["manifest"]["ready_for_memory_write"] is False
    assert payload["scenarios"]["manifest"]["apply_enabled"] is False
    assert payload["scenarios"]["manifest"]["local_brain_write"] is False
    assert payload["scenarios"]["selfhood_proposal"]["requires_user_approval"] is True
    assert payload["invariants"]["local_brain_write"] is False
    assert payload["invariants"]["raw_voice_saved"] is False
    assert any(tmp_path.glob("local_memory_approval_proof_*.json"))
