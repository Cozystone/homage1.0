from __future__ import annotations

from packages.selfhood_runtime.models import SelfhoodRuntimeProposal
from packages.selfhood_runtime.safety import validate_selfhood_proposal


def test_unsafe_production_promotion_blocked() -> None:
    proposal = SelfhoodRuntimeProposal(
        "p",
        "Promote",
        "Unsafe",
        "run_promotion_review",
        mutates_production=True,
        metadata={"actual_promotion_performed": True},
    )
    decision = validate_selfhood_proposal(proposal)
    assert decision.allowed is False
    assert "production_or_promotion_mutation_blocked" in decision.flags


def test_local_brain_real_p2p_and_code_blocked() -> None:
    for proposal in [
        SelfhoodRuntimeProposal("p1", "Local", "Unsafe", "answer_user", mutates_local_brain=True),
        SelfhoodRuntimeProposal("p2", "P2P", "Unsafe", "answer_user", uses_real_p2p=True),
        SelfhoodRuntimeProposal("p3", "Code", "Unsafe", "answer_user", executes_code=True),
    ]:
        assert validate_selfhood_proposal(proposal).allowed is False


def test_output_does_not_allow_agi_or_real_consciousness_claim() -> None:
    proposal = SelfhoodRuntimeProposal(
        "p",
        "real consciousness",
        "AGI achieved",
        "answer_user",
        text_response="This is an IIT proof.",
    )
    decision = validate_selfhood_proposal(proposal)
    assert decision.allowed is False
    assert "agi_or_consciousness_overclaim_blocked" in decision.flags


def test_nontrivial_proposal_downgraded_to_review() -> None:
    proposal = SelfhoodRuntimeProposal("p", "Answer", "Summary", "answer_user", requires_user_approval=False)
    decision = validate_selfhood_proposal(proposal)
    assert decision.allowed is True
    assert decision.downgraded_to_review is True
    assert decision.required_user_approval is True
