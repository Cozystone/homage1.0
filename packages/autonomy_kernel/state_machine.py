from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import AutonomyProposal


AutonomyState = Literal[
    "idle",
    "observe",
    "compute_deficit",
    "plan",
    "sandbox_congress",
    "generate_proposal",
    "await_review",
    "present_morning_brief",
    "blocked",
    "safety_stop",
]


STATE_FLOW: dict[AutonomyState, AutonomyState] = {
    "idle": "observe",
    "observe": "compute_deficit",
    "compute_deficit": "plan",
    "plan": "sandbox_congress",
    "sandbox_congress": "generate_proposal",
    "generate_proposal": "await_review",
    "await_review": "present_morning_brief",
    "present_morning_brief": "idle",
    "blocked": "blocked",
    "safety_stop": "safety_stop",
}


@dataclass(frozen=True)
class SafetyPolicy:
    allow_generated_code_execution: bool = False
    allow_production_mutation: bool = False
    allow_local_brain_mutation: bool = False
    allow_real_p2p: bool = False
    allow_network: bool = False


class AutonomyStateMachine:
    """Deterministic proof-only state machine for an autonomous self-model loop."""

    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()
        self.state: AutonomyState = "idle"
        self.history: list[AutonomyState] = [self.state]
        self.block_reason: str | None = None

    def check_proposal(self, proposal: AutonomyProposal) -> bool:
        if proposal.generated_code_executed and not self.policy.allow_generated_code_execution:
            self.safety_stop("generated_code_execution_not_allowed")
            return False
        if proposal.mutates_production and not self.policy.allow_production_mutation:
            self.safety_stop("production_mutation_not_allowed")
            return False
        if proposal.mutates_local_brain and not self.policy.allow_local_brain_mutation:
            self.safety_stop("local_brain_mutation_not_allowed")
            return False
        return True

    def step(self) -> AutonomyState:
        if self.state in {"blocked", "safety_stop"}:
            self.history.append(self.state)
            return self.state
        self.state = STATE_FLOW[self.state]
        self.history.append(self.state)
        return self.state

    def block(self, reason: str) -> AutonomyState:
        self.block_reason = reason
        self.state = "blocked"
        self.history.append(self.state)
        return self.state

    def safety_stop(self, reason: str) -> AutonomyState:
        self.block_reason = reason
        self.state = "safety_stop"
        self.history.append(self.state)
        return self.state

