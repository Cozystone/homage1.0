from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .autonomy_level import DEFAULT_PROOF_LEVEL, level_name
from .models import AutonomyLevelName, LifeCycleTick, TickType


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SimulatedLifeClock:
    """Deterministic local clock for proof and tests."""

    timestamp: str = "2026-06-22T00:00:00Z"
    counter: int = 0

    def tick(
        self,
        tick_type: TickType = "periodic_tick",
        reason: str = "simulated local lifecycle tick",
        autonomy_level: AutonomyLevelName = DEFAULT_PROOF_LEVEL,
    ) -> LifeCycleTick:
        self.counter += 1
        return LifeCycleTick(
            tick_id=f"tick-{self.counter:04d}",
            timestamp=self.timestamp,
            tick_type=tick_type,
            reason=reason,
            autonomy_level=level_name(autonomy_level),
        )


def make_tick(
    tick_type: TickType,
    reason: str,
    autonomy_level: AutonomyLevelName = DEFAULT_PROOF_LEVEL,
    timestamp: str | None = None,
    tick_id: str = "tick-0001",
) -> LifeCycleTick:
    return LifeCycleTick(
        tick_id=tick_id,
        timestamp=timestamp or utc_now_iso(),
        tick_type=tick_type,
        reason=reason,
        autonomy_level=level_name(autonomy_level),
    )
