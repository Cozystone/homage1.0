from packages.live_selfhood_cycle.models import Spark
from packages.live_selfhood_cycle.spark_metrics import compare_spark_effect, evaluate_sparks


def test_spark_metrics_compare_with_and_without_spark():
    sparks = [
        Spark("s1", "revisit_stale_candidate", "stale", 0.8, "low", "prepare_promotion_review"),
        Spark("s2", "prepare_status_brief", "brief", 0.7, "low", "prepare_morning_brief"),
    ]
    metrics = compare_spark_effect(["observe_status"], sparks)
    assert metrics["diversity_improved"] is True
    assert metrics["irreversible_actions"] == 0
    assert metrics["repeated_action_ratio"] == 0


def test_repeated_action_ratio_detects_looping():
    sparks = [
        Spark("s1", "prepare_status_brief", "brief", 0.7, "low", "prepare_morning_brief"),
        Spark("s2", "prepare_status_brief", "brief", 0.7, "low", "prepare_morning_brief"),
    ]
    metrics = evaluate_sparks(sparks, [])
    assert metrics["repeated_action_ratio"] == 0.5
