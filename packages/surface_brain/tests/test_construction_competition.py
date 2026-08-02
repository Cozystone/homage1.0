from __future__ import annotations

from packages.surface_brain.construction_graph import construction_candidates
from packages.surface_brain.realization_planner import plan_speech


def test_construction_selection_returns_multiple_candidates() -> None:
    candidates = construction_candidates("define", "ko", "beginner")

    assert len(candidates) >= 4
    assert {candidate["construction_id"] for candidate in candidates}


def test_planner_uses_competition_not_single_fixed_template(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan = plan_speech(
        "쿠버네티스가 뭐야?",
        {"concepts": ["Kubernetes", "containers"], "relations": [], "evidence": []},
        language="ko",
    )

    assert len(plan["trace"]["construction_candidates"]) > len(plan["selected_constructions"])
    assert len(plan["selected_constructions"]) >= 2
    assert plan["local_brain_write"] is False
