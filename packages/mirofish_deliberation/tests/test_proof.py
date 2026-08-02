from __future__ import annotations

from pathlib import Path

from packages.mirofish_deliberation.proof import run_proof


def test_mirofish_proof_writes_fixture_report(tmp_path):
    result = run_proof(tmp_path)

    assert all(result["summary"].values())
    assert result["invariants"]["production_store_mutated"] is False
    assert result["invariants"]["local_brain_write"] is False
    assert result["invariants"]["real_p2p_used"] is False
    assert Path(result["outputs"]["json"]).exists()
