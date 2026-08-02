from __future__ import annotations

from packages.surface_brain.realization_planner import plan_speech, realize_answer


def test_realization_applies_repair_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {}

    plan = plan_speech("Explain the system.", context, language="en")
    answer = realize_answer(plan, context, query="Explain the system.")

    assert "Cloud Brain" not in answer["answer"]
    assert answer["repair"]["applied"] in {True, False}
    assert "repair" in answer


def test_unrepaired_realization_keeps_before_for_comparison(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = {}

    plan = plan_speech("Explain the system.", context, language="en")
    answer = realize_answer(plan, context, query="Explain the system.", apply_repair=False)

    assert answer["repair"]["applied"] is False
