from pathlib import Path

from packages.graph_hub.proof import PROOF_JSON_PATH, run_graph_hub_proof


def test_graph_hub_proof_writes_artifacts():
    proof = run_graph_hub_proof()
    assert proof["passed"] is True
    assert proof["status"]["product_name"] == "Graph Hub"
    assert proof["export"]["old_mirror_snapshot_used"] is False
    assert Path(PROOF_JSON_PATH).exists()
