from __future__ import annotations

from pathlib import Path

from packages.turbovec_sandbox.proof import run_proof


def test_turbovec_proof_writes_fixture_report(tmp_path):
    result = run_proof(tmp_path)

    assert all(result["summary"].values())
    assert result["invariants"]["production_store_mutated"] is False
    assert Path(result["outputs"]["json"]).exists()
