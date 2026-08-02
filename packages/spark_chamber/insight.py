from __future__ import annotations

from packages.spark_chamber.models import ChaosBudget, MutationEvent, SparkInsight


def score_insight(source_input_id: str, event: MutationEvent, contradiction_pressure: float, loop_score: float) -> SparkInsight:
    """Score a candidate-only insight from a sandbox mutation."""

    novelty = min(1.0, 0.35 + contradiction_pressure + loop_score * 0.2)
    coherence = max(0.0, 0.9 - event.risk_score - contradiction_pressure * 0.2)
    usefulness = min(1.0, 0.45 + contradiction_pressure * 0.4 + (0.2 if event.mutation_type == "contradiction_probe" else 0.0))
    return SparkInsight(
        f"insight_{event.event_id}",
        source_input_id,
        f"{event.mutation_type} produced a reviewable candidate gap.",
        novelty,
        coherence,
        usefulness,
        event.risk_score,
        evidence=[event.to_dict(), {"contradiction_pressure": contradiction_pressure, "loop_score": loop_score}],
        limitations=["fixture-only", "candidate insight, not production knowledge"],
    )


def accept_insight(insight: SparkInsight, budget: ChaosBudget, novelty_threshold: float = 0.45, coherence_threshold: float = 0.45) -> bool:
    if insight.mutates_production or insight.mutates_local_brain:
        return False
    if not insight.candidate_only or not insight.requires_review:
        return False
    if insight.risk_score >= budget.max_risk_score:
        return False
    return insight.novelty_score > novelty_threshold and insight.coherence_score > coherence_threshold
