from __future__ import annotations

from packages.local_memory_operator_confirmation.proof import run_proof


def test_proof_scenarios(tmp_path) -> None:
    result = run_proof(tmp_path)
    scenarios = result["scenarios"]

    assert result["verdict"] == "PASS"
    assert scenarios["request_created"] is True
    assert scenarios["wrong_phrase_fails"] is True
    assert scenarios["correct_phrase_prepares_only"] is True
    assert scenarios["allowed_to_apply_real_write"] is False
    assert scenarios["apply_enabled"] is False
    assert scenarios["local_brain_write"] is False
    assert scenarios["missing_rollback_blocks"] is True
    assert scenarios["missing_sandbox_blocks"] is True
    assert scenarios["expired_request_blocks"] is True
