from __future__ import annotations

from pathlib import Path

from packages.answer_quality.comparison import get_run, run_answer_quality_benchmark


def test_comparison_runner_creates_three_candidate_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    run = run_answer_quality_benchmark(limit=4)
    payload = get_run(run["run_id"])

    assert run["total_prompts"] == 4
    assert run["average_scores"]["overall"] > 0
    assert payload is not None
    generators = {item["candidate"]["generator"] for item in payload["scored_candidates"]}
    assert {"baseline", "surface_brain", "repaired_surface_brain"}.issubset(generators)
    assert Path(f"data/answer_quality/reports/{run['run_id']}.md").exists()

