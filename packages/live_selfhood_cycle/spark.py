from __future__ import annotations

import hashlib
from typing import Any

from .freedom_budget import can_generate_spark
from .models import FreedomBudget, Need, Observation, RhythmState, Spark


def _random_unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def generate_spark(
    rhythm_state: RhythmState,
    observations: list[Observation],
    needs: list[Need],
    entropy_seed: str | None,
    budget: FreedomBudget | None = None,
) -> Spark | None:
    """Generate a bounded non-mutating spark."""

    if budget is not None and not can_generate_spark(budget):
        return None
    seed = entropy_seed or rhythm_state.rhythm_id
    threshold = min(0.35, 0.05 + rhythm_state.curiosity * 0.25 + rhythm_state.uncertainty * 0.15)
    if _random_unit(f"{seed}:spark:gate") > threshold and rhythm_state.curiosity < 0.85:
        return None
    stale = any(obs.payload.get("stale_candidate") for obs in observations)
    low_quality = any("quality" in need.need_type for need in needs)
    memory = any(need.need_type == "memory_review_needed" for need in needs)
    promotion = any(need.need_type == "promotion_review_needed" for need in needs)
    if stale:
        spark_type = "revisit_stale_candidate"
        action = "prepare_promotion_review"
        reason = "A stale candidate can be revisited without user prompting."
    elif low_quality:
        spark_type = "inspect_low_quality_answer"
        action = "run_mirofish_deliberation"
        reason = "Quality uncertainty suggests a local deliberation topic."
    elif memory:
        spark_type = "propose_memory_review"
        action = "prepare_memory_review"
        reason = "Memory backlog suggests a review proposal."
    elif promotion:
        spark_type = "propose_promotion_review"
        action = "prepare_promotion_review"
        reason = "Candidate backlog suggests a promotion review proposal."
    elif rhythm_state.user_presence > 0.6:
        spark_type = "prepare_status_brief"
        action = "prepare_morning_brief"
        reason = "User returned; prepare a status brief."
    elif rhythm_state.resource_pressure > 0.8:
        spark_type = "do_nothing"
        action = "do_nothing"
        reason = "Resource pressure is high; rest instead of proposing work."
    else:
        options: list[tuple[str, str, str]] = [
            ("start_mirofish_topic", "run_mirofish_deliberation", "Curiosity suggests a bounded local topic."),
            ("prepare_status_brief", "prepare_morning_brief", "Prepare a concise status brief."),
            ("ask_user_attention", "ask_user_attention", "Ask for attention on safe proposals."),
            ("do_nothing", "do_nothing", "No safe useful spark selected."),
        ]
        index = int(_random_unit(f"{seed}:spark:type") * len(options)) % len(options)
        spark_type, action, reason = options[index]
    risk = "high" if action in {"do_nothing", "ask_user_attention"} and rhythm_state.resource_pressure > 0.8 else "low"
    if risk == "high":
        spark_type = "do_nothing"
        action = "do_nothing"
    return Spark(
        spark_id=f"spark-{hashlib.sha1(f'{seed}:{spark_type}'.encode('utf-8')).hexdigest()[:10]}",
        spark_type=spark_type,  # type: ignore[arg-type]
        trigger_reason=reason,
        novelty_score=round(0.35 + _random_unit(f"{seed}:novelty") * 0.65, 6),
        risk_level=risk,  # type: ignore[arg-type]
        proposed_action_type=action,  # type: ignore[arg-type]
        requires_user_approval=True,
        can_mutate=False,
        can_execute=False,
    )


def block_unsafe_spark(payload: dict[str, Any]) -> Spark:
    """Downgrade an unsafe forced spark into a safe attention request."""

    return Spark(
        spark_id="spark-blocked-unsafe",
        spark_type="ask_user_attention",
        trigger_reason=f"Unsafe spark blocked: {payload.get('requested', 'unknown')}",
        novelty_score=0.0,
        risk_level="high",
        proposed_action_type="ask_user_attention",
        requires_user_approval=True,
        can_mutate=False,
        can_execute=False,
    )
