from __future__ import annotations

from pathlib import Path

from packages.ego_network.proof import run_proof


def test_proof_writes_report_and_all_scenarios_pass(tmp_path: Path) -> None:
    results = run_proof(tmp_path)
    assert all(results["summary"].values())
    assert Path(results["outputs"]["json"]).exists()
    assert Path(results["outputs"]["md"]).exists()
    assert results["safety"]["production_store_mutated"] is False
    assert results["safety"]["local_brain_write"] is False
    assert results["safety"]["real_p2p_used"] is False
    assert results["safety"]["real_cloud_upload"] is False
