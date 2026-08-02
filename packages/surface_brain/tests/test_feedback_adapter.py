from __future__ import annotations

from pathlib import Path

from packages.surface_brain.feedback_adapter import convert_answer_quality_feedback_to_repair_candidates


def test_trace_leakage_feedback_creates_enabled_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    candidates = convert_answer_quality_feedback_to_repair_candidates(
        [{"feedback_id": "f1", "type": "repair_pattern", "suggestion": "Apply remove_internal_path_leakage before rendering."}],
        "run-1",
    )

    assert candidates
    assert candidates[0]["enabled"] is True
    assert candidates[0]["source"] == "answer_quality_feedback"
    assert "Cloud Brain" in candidates[0]["trigger_terms"]
    assert Path("data/surface_brain/repair_candidates/repair_candidates_run-1.json").exists()


def test_style_feedback_remains_review_only(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    candidates = convert_answer_quality_feedback_to_repair_candidates(
        [{"feedback_id": "f2", "type": "language_native_style", "suggestion": "Korean unnatural wording."}],
        "run-2",
    )

    assert candidates
    assert candidates[0]["enabled"] is False
    assert candidates[0]["action"] == "rewrite_sentence"
