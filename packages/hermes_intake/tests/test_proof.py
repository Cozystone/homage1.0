from packages.hermes_intake.proof import run_proof


def test_hermes_intake_proof_generates_files(tmp_path):
    result = run_proof(tmp_path)
    assert result["passed"] is True
    assert (tmp_path / "hermes_intake_proof.json").exists()
    assert result["report"]["hermes_code_executed_before_review"] is False
