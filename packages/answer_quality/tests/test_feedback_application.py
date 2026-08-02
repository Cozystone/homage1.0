from __future__ import annotations

from packages.answer_quality.comparison import run_answer_quality_benchmark
from packages.surface_brain.feedback_adapter import convert_answer_quality_feedback_to_repair_candidates


def test_answer_quality_feedback_can_be_converted_without_auto_promotion(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    run = run_answer_quality_benchmark(limit=8)
    candidates = convert_answer_quality_feedback_to_repair_candidates(run["surface_feedback"], run["run_id"])

    assert candidates
    assert all(candidate["source"] == "answer_quality_feedback" for candidate in candidates)
    assert any(candidate["enabled"] for candidate in candidates)
    assert run["honesty"]["auto_promoted_feedback"] is False
