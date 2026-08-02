from __future__ import annotations

from packages.spark_chamber.homeostasis import decide_homeostasis


def test_homeostasis_reduces_chaos_under_high_pressure() -> None:
    decision = decide_homeostasis({"disk_free_gib": 80.0}, contradiction_pressure=0.8, mutation_pressure=0.8, uncertainty=0.2, user_goal_pressure=0.2)
    assert decision.action == "reduce_chaos"


def test_homeostasis_pauses_under_resource_pressure() -> None:
    decision = decide_homeostasis({"disk_free_gib": 10.0}, contradiction_pressure=0.1, mutation_pressure=0.1, uncertainty=0.2, user_goal_pressure=0.2)
    assert decision.action == "pause_mutation"
