from __future__ import annotations

from pathlib import Path

from packages.selfhood_runtime.proof import run_proof


def test_proof_command_writes_report(tmp_path: Path) -> None:
    proof = run_proof(tmp_path)
    assert proof["verdict"] == "SELFHOOD_RUNTIME_V0_PROOF_ONLY"
    assert proof["scenario_count"] == 8
    assert proof["invariants"]["production_store_mutated"] is False
    assert proof["invariants"]["local_brain_write"] is False
    assert proof["invariants"]["real_p2p_used"] is False
    assert Path(proof["outputs"]["json"]).exists()
    assert Path(proof["outputs"]["md"]).exists()
