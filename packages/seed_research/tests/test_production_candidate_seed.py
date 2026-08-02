from __future__ import annotations

from pathlib import Path

from seed_research.production_candidate import (
    REQUIRED_CATEGORIES,
    build_seed_candidates,
    evaluate_candidate,
    run_seed_graph_research,
)


def test_candidate_series_and_best_current_contract() -> None:
    candidates = build_seed_candidates()
    candidate_ids = [candidate["candidate_id"] for candidate in candidates]

    assert candidate_ids == [
        "seed_v26_minimal_core",
        "seed_v27_grounding_core",
        "seed_v28_style_bridge",
        "seed_v29_internal_architecture",
        "seed_v30_external_bridge",
        "seed_v31_outlier_strict",
        "seed_v32_korean_native_strict",
        "seed_v33_grounded_answer_planner",
        "seed_v34_trace_hygiene_strict",
        "seed_v35_best_current",
    ]
    best = candidates[-1]
    assert best["production_status"] == "reviewable_candidate"
    assert best["canned_final_answers"] is False
    assert best["external_llm_used"] is False
    assert best["external_sllm_used"] is False


def test_best_candidate_covers_required_categories_without_duplicate_ids() -> None:
    best = build_seed_candidates()[-1]
    categories = {node["category"] for node in best["nodes"]}
    node_ids = [node["id"] for node in best["nodes"]]

    assert set(REQUIRED_CATEGORIES).issubset(categories)
    assert len(node_ids) == len(set(node_ids))


def test_best_candidate_relations_are_valid_and_not_dead() -> None:
    best = build_seed_candidates()[-1]
    evaluation = evaluate_candidate(best)

    assert evaluation["relation_endpoints_valid"] is True
    assert evaluation["dead_node_ratio"] <= 0.05
    assert evaluation["scores"]["trace_hygiene"] == 1.0
    assert evaluation["scores"]["template_smell"] >= 0.95
    assert evaluation["scores"]["overall"] >= 0.94
    assert evaluation["scores"]["korean_native"] >= 0.92
    assert evaluation["strict_target_passed"] is True


def test_seed_graph_research_writes_reviewable_artifacts(tmp_path: Path) -> None:
    result = run_seed_graph_research(output_root=tmp_path, timestamp="20260618_000000")

    assert result["best_candidate_id"] == "seed_v35_best_current"
    assert result["target_passed"] is True
    assert Path(result["candidate_path"]).exists()
    assert Path(result["experiment_path"]).exists()
    assert Path(result["report_path"]).exists()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "not as an automatic production overwrite" in report
    assert "not a prompt-specific answer template engine" in report
