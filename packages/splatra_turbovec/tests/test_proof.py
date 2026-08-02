import json

from packages.splatra_turbovec.proof import run_proof


def test_proof_files_generated(tmp_path):
    result = run_proof(tmp_path)
    assert result["passed"] is True
    json_path = tmp_path / "splatra_turbovec_proof.json"
    md_path = tmp_path / "splatra_turbovec_proof.md"
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["invariants"]["proof_only"] is True
    assert payload["city"]["particles"] == 200_000
