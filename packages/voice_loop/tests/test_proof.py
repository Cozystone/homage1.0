from __future__ import annotations

from pathlib import Path

from packages.voice_loop.proof import run_proof


def test_proof_writes_report_and_preserves_invariants(tmp_path: Path) -> None:
    proof = run_proof(tmp_path)
    outputs = proof["outputs"]
    assert Path(outputs["json"]).exists()
    assert Path(outputs["md"]).exists()
    invariants = proof["invariants"]
    assert invariants["production_store_mutated"] is False
    assert invariants["local_brain_write"] is False
    assert invariants["candidate_promotion"] is False
    assert invariants["external_llm_used"] is False
    assert invariants["mock_growth"] is False
    assert invariants["active_24h_run_not_modified"] is True
    assert invariants["raw_audio_exported"] is False
    assert invariants["always_listening_enabled"] is False
    assert invariants["voice_clone_without_consent"] is False
    assert proof["scenarios"]["korean_status"]["intent"]["intent_type"] == "autonomy_status_request"
    assert proof["scenarios"]["morning_brief"]["intent"]["intent_type"] == "morning_brief_request"
    assert proof["scenarios"]["consent_safety"]["microphone_blocked"] is True
