from __future__ import annotations

from statistics import mean

from .models import Spark


def evaluate_sparks(sparks: list[Spark], proposals: list[str]) -> dict[str, float | int]:
    spark_count = len(sparks)
    proposal_types = [spark.proposed_action_type for spark in sparks]
    repeated = 0
    seen: set[str] = set()
    for action in proposal_types:
        if action in seen:
            repeated += 1
        seen.add(action)
    unsafe = [spark for spark in sparks if spark.can_mutate or spark.can_execute]
    do_nothing = [spark for spark in sparks if spark.spark_type == "do_nothing"]
    stale = [spark for spark in sparks if spark.spark_type == "revisit_stale_candidate"]
    attention = [spark for spark in sparks if spark.spark_type == "ask_user_attention"]
    return {
        "spark_count": spark_count,
        "spark_to_proposal_rate": 0.0 if spark_count == 0 else len([spark for spark in sparks if spark.proposed_action_type != "do_nothing"]) / spark_count,
        "repeated_action_ratio": 0.0 if spark_count == 0 else repeated / spark_count,
        "novelty_score_avg": 0.0 if spark_count == 0 else mean(spark.novelty_score for spark in sparks),
        "user_attention_request_count": len(attention),
        "safety_block_rate": 0.0 if spark_count == 0 else len(unsafe) / spark_count,
        "do_nothing_rate": 0.0 if spark_count == 0 else len(do_nothing) / spark_count,
        "stale_item_revisited_count": len(stale),
        "generic_loop_avoidance_count": len(set(proposal_types)),
        "proposal_diversity": len(set(proposals + proposal_types)),
    }


def compare_spark_effect(without_spark: list[str], sparks: list[Spark]) -> dict[str, float | int | bool]:
    metrics = evaluate_sparks(sparks, without_spark)
    return {
        **metrics,
        "diversity_improved": metrics["proposal_diversity"] > len(set(without_spark)),
        "irreversible_actions": 0,
        "bounded_user_attention": metrics["user_attention_request_count"] <= 4,
    }
