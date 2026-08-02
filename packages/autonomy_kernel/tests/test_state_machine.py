from __future__ import annotations

from packages.autonomy_kernel.models import AutonomyProposal
from packages.autonomy_kernel.state_machine import AutonomyStateMachine


def test_state_transitions_deterministic() -> None:
    machine = AutonomyStateMachine()
    assert [machine.step() for _ in range(4)] == ["observe", "compute_deficit", "plan", "sandbox_congress"]


def test_safety_stop_on_attempted_mutation() -> None:
    machine = AutonomyStateMachine()
    proposal = AutonomyProposal("p", "code_patch_proposal", "Unsafe", "Summary", "Rationale", mutates_production=True)
    assert machine.check_proposal(proposal) is False
    assert machine.state == "safety_stop"
    assert machine.block_reason == "production_mutation_not_allowed"

