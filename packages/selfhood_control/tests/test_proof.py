from __future__ import annotations

from pathlib import Path

from packages.selfhood_control.proof import run_proof


def test_proof_command_writes_report(tmp_path: Path) -> None:
    proof = run_proof(tmp_path)
    assert proof["passed"] is True
    assert Path(proof["outputs"]["json"]).exists()
    assert Path(proof["outputs"]["md"]).exists()
    invariants = proof["invariants"]
    assert invariants["production_store_mutated"] is False
    assert invariants["local_brain_write"] is False
    assert invariants["candidate_promotion"] is False
    assert invariants["external_llm_used"] is False
    assert invariants["pair_edges_sent"] == 0
    assert invariants["active_24h_run_not_modified"] is True
