from __future__ import annotations

from pathlib import Path

from packages.surface_brain.proof_review_queue import run_surface_repair_review_queue_proof


def test_review_queue_proof_files_generated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_surface_repair_review_queue_proof()

    assert result["pass"] is True
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    assert result["honesty"]["auto_promoted"] is False
