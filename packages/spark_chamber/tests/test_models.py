from __future__ import annotations

import pytest

from packages.spark_chamber.models import ChaosBudget, MutationEvent, SparkInput, SparkInsight


def test_model_validation() -> None:
    with pytest.raises(ValueError):
        SparkInput("", "proof_fixture", {})
    with pytest.raises(ValueError):
        ChaosBudget(1.2, 1)
    with pytest.raises(ValueError):
        ChaosBudget(0.2, 1, production_mutation_allowed=True)


def test_mutation_event_rejects_production_or_local_application() -> None:
    with pytest.raises(ValueError):
        MutationEvent("m", "phase_jitter", {}, {}, 0.1, True, applied_to_production=True)
    with pytest.raises(ValueError):
        MutationEvent("m", "phase_jitter", {}, {}, 0.1, True, applied_to_local_brain=True)


def test_insight_is_candidate_only() -> None:
    insight = SparkInsight("i", "s", "candidate", 0.6, 0.8, 0.7, 0.1)
    assert insight.candidate_only is True
    assert insight.requires_review is True
    with pytest.raises(ValueError):
        SparkInsight("i", "s", "bad", 0.6, 0.8, 0.7, 0.1, candidate_only=False)
