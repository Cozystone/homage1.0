from __future__ import annotations

from pathlib import Path

from packages.answer_quality.surface_feedback import generate_surface_feedback


def test_feedback_generated_but_not_auto_promoted(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rows = [
        {
            "prompt": {"prompt_id": "p1"},
            "candidate": {"generator": "surface_brain"},
            "score": {"flags": ["template_opening_overused"], "template_smell": 0.2},
        }
    ]

    feedback = generate_surface_feedback("run1", rows)

    assert feedback
    assert feedback[0]["auto_promoted"] is False
    assert Path("data/answer_quality/feedback/surface_feedback_run1.json").exists()

