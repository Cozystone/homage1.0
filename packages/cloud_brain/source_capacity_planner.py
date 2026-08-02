from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SourceCapacityPlan:
    """Capacity verdict for a target-rate candidate-only learning run."""

    can_run_full_duration: bool
    estimated_duration_at_rate: float
    required_rows_for_duration: int
    available_rows: int
    recommended_target_rate: float
    recommended_duration: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable capacity plan."""

        return asdict(self)


def plan_source_capacity(
    *,
    source_rows: int,
    accepted_estimate: int | None = None,
    target_duration_seconds: int,
    target_payloads_per_second: float,
    min_payloads_required: int | None = None,
    candidate_store_cap_mb: float | None = None,
) -> SourceCapacityPlan:
    """Return whether approved rows can sustain a target-rate run.

    The planner only reasons about already approved local payload rows.  It does
    not crawl, fabricate, or assume future source availability.
    """

    available = max(0, int(accepted_estimate if accepted_estimate is not None else source_rows))
    duration = max(0, int(target_duration_seconds))
    target_rate = max(0.0, float(target_payloads_per_second))
    required = int(duration * target_rate)
    if min_payloads_required is not None:
        required = max(required, int(min_payloads_required))
    if duration <= 0:
        return SourceCapacityPlan(False, 0.0, required, available, 0.0, 0.0, "target_duration_required")
    if target_rate <= 0:
        return SourceCapacityPlan(False, 0.0, required, available, 0.0, 0.0, "target_rate_required")

    estimated_duration = available / target_rate if target_rate > 0 else 0.0
    cap_payload_estimate = None
    if candidate_store_cap_mb is not None and candidate_store_cap_mb > 0:
        # Conservative planning hook: 0.01 MiB/payload is intentionally high
        # enough to avoid promising long runs from tiny candidate-store caps.
        cap_payload_estimate = int(float(candidate_store_cap_mb) / 0.01)
    cap_limited = cap_payload_estimate is not None and cap_payload_estimate < required
    can_run = available >= required and not cap_limited

    if can_run:
        reason = "enough_rows_for_target_duration"
        recommended_rate = target_rate
        recommended_duration = float(duration)
    elif cap_limited:
        reason = "candidate_store_cap_too_small_for_target_duration"
        recommended_rate = min(target_rate, max(0.0, float(cap_payload_estimate or 0) / max(1, duration)))
        recommended_duration = float(cap_payload_estimate or 0) / target_rate if target_rate > 0 else 0.0
    else:
        reason = "insufficient_source_rows_for_target_duration"
        recommended_rate = min(target_rate, available / duration) if duration > 0 else 0.0
        recommended_duration = estimated_duration

    return SourceCapacityPlan(
        can_run_full_duration=can_run,
        estimated_duration_at_rate=round(estimated_duration, 6),
        required_rows_for_duration=required,
        available_rows=available,
        recommended_target_rate=round(recommended_rate, 6),
        recommended_duration=round(recommended_duration, 6),
        reason=reason,
    )
