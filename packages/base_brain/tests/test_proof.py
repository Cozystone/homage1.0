from packages.base_brain.models import PROOF_JSON_PATH, PROOF_MD_PATH
from packages.base_brain.proof import run_base_brain_proof


def test_base_brain_proof_writes_artifacts() -> None:
    result = run_base_brain_proof()
    assert result["status"] == "PASS"
    assert PROOF_JSON_PATH.exists()
    assert PROOF_MD_PATH.exists()
    assert result["useful_answer_count"] >= 7
    assert result["external_llm_used"] is False
