from packages.agentic_micro_os.proof import run_proof


def test_agentic_micro_os_proof_generates_files(tmp_path):
    result = run_proof(tmp_path)
    assert result["passed"] is True
    assert result["auto_commit_blocked"] is True
    assert result["auto_push_blocked"] is True
    assert (tmp_path / "agentic_micro_os_proof.json").exists()
