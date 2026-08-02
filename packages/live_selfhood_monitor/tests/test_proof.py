from pathlib import Path

from packages.live_selfhood_monitor.proof import run_proof


def test_proof_scenarios_pass(tmp_path: Path) -> None:
    result = run_proof(tmp_path)
    assert result["verdict"] == "PASS"
    assert all(result["scenarios"].values())
    assert Path(result["outputs"]["json"]).exists()
