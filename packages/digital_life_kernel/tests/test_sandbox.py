from __future__ import annotations

from packages.digital_life_kernel.models import LifeActionProposal
from packages.digital_life_kernel.sandbox import simulate_proposal


def test_sandbox_passes_safe_proposal():
    result = simulate_proposal(LifeActionProposal("p", "do_nothing", "Idle", "No action.", "low"))

    assert result.passed is True
    assert result.safety_report["production_store_mutated"] is False


def test_sandbox_blocks_production_mutation():
    proposal = LifeActionProposal(
        "p",
        "propose_promotion_review",
        "Unsafe",
        "Fixture.",
        "blocked",
        mutates_production=True,
    )

    result = simulate_proposal(proposal)

    assert result.passed is False
    assert "production_mutation_blocked" in result.blocked_reason
