from __future__ import annotations

from pathlib import Path

from packages.answer_quality.benchmark_set import CORE_SET_NAME, ensure_default_benchmark_set


def test_default_benchmark_set_has_required_size_and_categories(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    benchmark = ensure_default_benchmark_set()
    categories = {prompt["category"] for prompt in benchmark["prompts"]}

    assert benchmark["name"] == CORE_SET_NAME
    assert len(benchmark["prompts"]) >= 50
    assert {"general_knowledge", "project_style", "trace_leakage", "grounded_answer"}.issubset(categories)
    assert Path("data/answer_quality/benchmark_sets/core_ko_en_v1.json").exists()

