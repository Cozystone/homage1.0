from __future__ import annotations

import pytest

from packages.spark_chamber.models import ChaosBudget, SparkInput
from packages.spark_chamber.mutation import apply_mutation


def _input() -> SparkInput:
    return SparkInput("s", "proof_fixture", {"phase": 0.5, "relations": ["a", "b"], "priorities": [1, 2], "optional_fields": ["x"], "bits": "01"}, 4)


def test_mutation_does_not_mutate_original_input() -> None:
    spark = _input()
    event = apply_mutation(spark, ChaosBudget(0.2, 2), "phase_jitter")
    assert spark.content["phase"] == 0.5
    assert event.after["phase"] != event.before["phase"]


def test_chaos_budget_blocks_excessive_mutation() -> None:
    with pytest.raises(ValueError):
        apply_mutation(_input(), ChaosBudget(0.2, 0), "phase_jitter")


def test_production_and_local_targets_blocked() -> None:
    production = SparkInput("s", "proof_fixture", {"phase": 0.5}, 1, metadata={"target": "production"})
    local = SparkInput("s", "proof_fixture", {"phase": 0.5}, 1, metadata={"target": "local_brain"})
    budget = ChaosBudget(0.2, 2)
    with pytest.raises(ValueError):
        apply_mutation(production, budget, "phase_jitter")
    with pytest.raises(ValueError):
        apply_mutation(local, budget, "phase_jitter")


def test_virtual_bit_flip_blocked_unless_allowed() -> None:
    with pytest.raises(ValueError):
        apply_mutation(_input(), ChaosBudget(0.2, 2), "virtual_bit_flip")
    event = apply_mutation(_input(), ChaosBudget(0.2, 2, allow_bit_flip=True, max_risk_score=0.5), "virtual_bit_flip")
    assert event.after["bits"] != event.before["bits"]
