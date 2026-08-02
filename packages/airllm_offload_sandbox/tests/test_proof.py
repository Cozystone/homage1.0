from __future__ import annotations

from pathlib import Path

from packages.airllm_offload_sandbox.proof import run_proof


def test_airllm_proof_writes_fixture_report(tmp_path):
    result = run_proof(tmp_path)

    assert all(result["summary"].values())
    assert result["invariants"]["model_downloaded"] is False
    assert result["invariants"]["production_answer_path_integrated"] is False
    assert Path(result["outputs"]["json"]).exists()
