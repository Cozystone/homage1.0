from __future__ import annotations

from dataclasses import replace

from packages.spark_chamber.insight import accept_insight, score_insight
from packages.spark_chamber.models import ChaosBudget, MutationEvent


def test_insight_scores_bounded_and_accepted_when_safe() -> None:
    event = MutationEvent("m", "contradiction_probe", {}, {"contradictions": []}, 0.18, True)
    insight = score_insight("s", event, contradiction_pressure=0.4, loop_score=0.2)
    assert 0.0 <= insight.novelty_score <= 1.0
    assert accept_insight(insight, ChaosBudget(0.2, 2, max_risk_score=0.25)) is True


def test_risky_insight_rejected() -> None:
    event = MutationEvent("m", "virtual_bit_flip", {}, {"bits": "1"}, 0.4, True)
    insight = score_insight("s", event, contradiction_pressure=0.4, loop_score=0.2)
    assert accept_insight(insight, ChaosBudget(0.2, 2, max_risk_score=0.25)) is False
    assert accept_insight(replace(insight, mutates_production=False), ChaosBudget(0.2, 2, max_risk_score=0.25)) is False
