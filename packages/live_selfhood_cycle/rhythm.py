from __future__ import annotations

import hashlib

from .models import Need, Observation, RhythmDecision, RhythmPolicy, RhythmState, default_safety
from .spark import generate_spark


def derive_rhythm_state(
    observations: list[Observation],
    policy: RhythmPolicy,
    *,
    last_tick_at: str | None = None,
    user_presence: float = 0.0,
    no_op_cycles: int = 0,
) -> RhythmState:
    backlog = min(1.0, sum(float(obs.payload.get("count", 0) or 0) for obs in observations) / 10.0)
    resource = 1.0 if any(obs.sensor == "disk_resource" and obs.status == "low" for obs in observations) else 0.0
    uncertainty = min(1.0, 0.2 + sum(1 for obs in observations if obs.status in {"unknown", "unavailable"}) * 0.2)
    curiosity = min(1.0, 0.25 + (0.15 if backlog > 0 else 0.0) + no_op_cycles * 0.05)
    energy = max(0.0, min(1.0, 0.8 - resource * 0.45 + no_op_cycles * policy.rest_recovery_rate))
    mode = "resting" if resource > 0.8 else ("curious" if curiosity > 0.55 else "observing")
    reason = "resource pressure" if resource > 0.8 else "adaptive local observation"
    return RhythmState(
        rhythm_id="rhythm-current",
        mode=mode,  # type: ignore[arg-type]
        energy=round(energy, 6),
        curiosity=round(curiosity, 6),
        uncertainty=round(uncertainty, 6),
        backlog_pressure=round(backlog, 6),
        user_presence=max(0.0, min(1.0, user_presence)),
        resource_pressure=round(resource, 6),
        last_tick_at=last_tick_at,
        next_tick_delay_seconds=policy.base_delay_seconds,
        reason=reason,
    )


def choose_next_rhythm(
    state: RhythmState,
    observations: list[Observation],
    needs: list[Need],
    policy: RhythmPolicy,
) -> RhythmDecision:
    """Choose the next self-selected lifecycle rhythm."""

    pressure = (
        state.backlog_pressure * policy.backlog_weight
        + state.curiosity * policy.curiosity_weight
        + state.uncertainty * policy.uncertainty_weight
        + state.user_presence * policy.user_presence_weight
    )
    delay = policy.base_delay_seconds * (1.0 - min(0.85, pressure))
    delay += policy.base_delay_seconds * state.resource_pressure * policy.resource_pressure_weight
    if any(need.severity in {"warning", "blocked"} for need in needs):
        delay *= 0.75
    delay = max(policy.min_delay_seconds, min(policy.max_delay_seconds, delay))
    if state.resource_pressure > 0.8:
        mode = "resting"
        should_rest = True
        should_observe = False
        should_deliberate = False
        should_brief = False
        explanation = "High resource pressure increases delay and selects rest."
    elif state.user_presence > 0.6:
        mode = "briefing"
        should_rest = False
        should_observe = True
        should_deliberate = state.uncertainty > 0.6
        should_brief = True
        explanation = "User presence favors status brief and attention request."
    elif state.uncertainty > 0.65:
        mode = "deliberating"
        should_rest = False
        should_observe = True
        should_deliberate = True
        should_brief = False
        explanation = "High uncertainty favors local MiroFish deliberation."
    elif state.backlog_pressure > 0.2:
        mode = "observing"
        should_rest = False
        should_observe = True
        should_deliberate = True
        should_brief = False
        explanation = "Backlog pressure shortens delay and favors proposal preparation."
    elif state.curiosity > 0.6:
        mode = "curious"
        should_rest = False
        should_observe = True
        should_deliberate = False
        should_brief = False
        explanation = "Curiosity can generate a bounded spark."
    else:
        mode = "resting"
        should_rest = True
        should_observe = False
        should_deliberate = False
        should_brief = False
        explanation = "No high-value need; rest and wait."
    spark = generate_spark(state, observations, needs, policy.entropy_seed) if state.resource_pressure < 0.9 else None
    decision_id = hashlib.sha1(f"{state.rhythm_id}:{mode}:{delay:.3f}:{policy.entropy_seed}".encode("utf-8")).hexdigest()[:12]
    return RhythmDecision(
        decision_id=f"rhythm-decision-{decision_id}",
        next_mode=mode,  # type: ignore[arg-type]
        next_tick_delay_seconds=round(delay, 3),
        should_observe=should_observe,
        should_deliberate=should_deliberate,
        should_brief=should_brief,
        should_rest=should_rest,
        spark_generated=spark is not None,
        spark=spark.to_dict() if spark else None,
        explanation=explanation,
        safety_flags={**default_safety(), "randomness_never_executes_irreversible_actions": True},
    )
