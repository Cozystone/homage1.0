from __future__ import annotations

from pathlib import Path

from packages.spark_chamber.proof import run_proof


def test_proof_writes_report_and_triage(tmp_path: Path) -> None:
    proof = run_proof(tmp_path)
    assert proof["passed"] is True
    assert Path(proof["outputs"]["json"]).exists()
    assert Path(proof["outputs"]["md"]).exists()
    assert Path(proof["outputs"]["triage"]).exists()
    assert proof["scenarios"]["deterministic_spark"] is True
    assert proof["scenarios"]["risky_mutation_rejected"] is True
    assert proof["invariants"]["production_store_mutated"] is False
    assert proof["invariants"]["local_brain_write"] is False
    assert proof["invariants"]["candidate_store_mutated"] is False
    assert proof["invariants"]["external_llm_used"] is False
