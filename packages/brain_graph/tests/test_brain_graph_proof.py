from pathlib import Path

from packages.brain_graph.models import PROOF_JSON_PATH, PROOF_MD_PATH
from packages.brain_graph.proof import run_tab_aware_brain_graph_proof


def test_tab_aware_brain_graph_proof_files_created():
    proof = run_tab_aware_brain_graph_proof()
    assert proof["passed"] is True
    assert Path(PROOF_JSON_PATH).exists()
    assert Path(PROOF_MD_PATH).exists()
