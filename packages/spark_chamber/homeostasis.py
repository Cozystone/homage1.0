from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


HomeostasisAction = Literal["continue", "reduce_chaos", "pause_mutation", "ask_user", "self_heal_proposal", "blocked"]


@dataclass(frozen=True)
class HomeostasisDecision:
    action: HomeostasisAction
    reason: str
    safety_notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_homeostasis(
    resource_state: dict[str, float],
    contradiction_pressure: float,
    mutation_pressure: float,
    uncertainty: float,
    user_goal_pressure: float,
) -> HomeostasisDecision:
    """Balance Spark Chamber pressure as a control policy, not a survival claim."""

    disk = float(resource_state.get("disk_free_gib", 999.0))
    if disk < 20.0:
        return HomeostasisDecision("pause_mutation", "disk pressure too high", ["protect runtime", "ask before more experiments"])
    if mutation_pressure > 0.7 or contradiction_pressure > 0.7:
        return HomeostasisDecision("reduce_chaos", "mutation or contradiction pressure high", ["lower chaos budget"])
    if uncertainty > 0.8 and user_goal_pressure > 0.5:
        return HomeostasisDecision("ask_user", "uncertainty affects user goal", ["proposal-only"])
    if contradiction_pressure > 0.45:
        return HomeostasisDecision("self_heal_proposal", "contradiction review suggested", ["review only", "no automatic repair"])
    return HomeostasisDecision("continue", "pressure within proof budget", ["candidate-only"])
