from __future__ import annotations

from pathlib import Path

from packages.answer_quality.comparison import run_repair_comparison


def test_repair_comparison_reports_trace_hygiene_improvement(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_repair_comparison(limit=8)

    assert result["trace_hygiene_after"] >= result["trace_hygiene_before"]
    assert result["repairs_applied"] >= 1
    assert result["auto_promoted_feedback"] is False
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
