from pathlib import Path

from packages.live_selfhood_cycle.proof import run_proof


def test_proof_passes_and_writes_outputs(tmp_path: Path):
    result = run_proof(tmp_path)
    assert result["verdict"] == "PASS"
    assert all(result["scenarios"].values())
    assert Path(result["outputs"]["json"]).exists()
    assert Path(result["outputs"]["md"]).exists()
