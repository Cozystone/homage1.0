from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import LifeActionProposal


@dataclass(frozen=True)
class SandboxResult:
    proposal_id: str
    passed: bool
    blocked_reason: str | None
    safety_report: dict[str, Any]
    expected_effect: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_proposal(proposal: LifeActionProposal) -> SandboxResult:
    """Simulate a proposal without applying changes."""

    violations = []
    if proposal.mutates_production:
        violations.append("production_mutation_blocked")
    if proposal.mutates_local_brain:
        violations.append("local_brain_write_blocked")
    if proposal.uses_real_p2p:
        violations.append("real_p2p_blocked")
    if proposal.generated_code_executed:
        violations.append("generated_code_execution_blocked")
    if not proposal.requires_user_approval:
        violations.append("missing_user_approval_gate")

    passed = not violations
    return SandboxResult(
        proposal.action_id,
        passed,
        None if passed else ",".join(violations),
        {
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "mock_growth": False,
            "real_p2p_used": False,
            "raw_private_data_exported": False,
            "generated_code_executed": False,
            "real_hot_swap_performed": False,
            "violations": violations,
        },
        {"mode": "proposal_only", "applied": False, "requires_review": True},
    )
