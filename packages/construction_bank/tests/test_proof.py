from __future__ import annotations

from packages.construction_bank.proof import run_proof


def test_proof_reports_safe_invariants() -> None:
    proof = run_proof()
    assert proof["external_llm"] is False
    assert proof["production_store_mutated"] is False
    assert proof["construction_auto_promoted"] is False
    assert proof["production_active_count"] == 0
