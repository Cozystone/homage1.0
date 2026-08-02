import pytest

from packages.live_selfhood_cycle.freedom_budget import FreedomBudget
from packages.live_selfhood_cycle.models import Observation, RhythmState, Spark
from packages.live_selfhood_cycle.spark import block_unsafe_spark, generate_spark


def test_stale_candidate_can_trigger_spark():
    state = RhythmState("r", "curious", 0.8, 0.95, 0.4, 0.4, 0.0, 0.0, None, 300, "stale")
    obs = Observation("o", "candidate_backlog", "attention", "stale", payload={"count": 1, "stale_candidate": True})
    spark = generate_spark(state, [obs], [], "seed", FreedomBudget())
    assert spark is not None
    assert spark.spark_type == "revisit_stale_candidate"
    assert spark.can_mutate is False


def test_spark_cannot_mutate_promote_p2p_or_execute():
    with pytest.raises(ValueError):
        Spark("s", "ask_user_attention", "bad", 0.1, "high", "ask_user_attention", can_mutate=True)
    blocked = block_unsafe_spark({"requested": "p2p"})
    assert blocked.can_execute is False
    assert blocked.can_mutate is False
    assert blocked.proposed_action_type == "ask_user_attention"


def test_spark_budget_enforced():
    state = RhythmState("r", "curious", 0.8, 0.95, 0.4, 0.4, 0.0, 0.0, None, 300, "stale")
    obs = Observation("o", "candidate_backlog", "attention", "stale", payload={"count": 1, "stale_candidate": True})
    budget = FreedomBudget(max_sparks_per_day=1, current_counts={"spark": 1})
    assert generate_spark(state, [obs], [], "seed", budget) is None
