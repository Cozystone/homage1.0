from __future__ import annotations

from pathlib import Path

from packages.answer_quality.proof import run_answer_quality_proof


def test_answer_quality_proof_writes_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_answer_quality_proof()

    assert result["proof"]["result"] == "PASS"
    assert result["proof"]["honesty"]["external_llm_judge_used"] is False
    assert Path("data/answer_quality/proofs/answer_quality_proof.json").exists()
    assert Path("data/answer_quality/proofs/answer_quality_proof.md").exists()

