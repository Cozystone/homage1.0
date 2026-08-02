from __future__ import annotations

from packages.mirofish_deliberation.models import DeliberationInput
from packages.mirofish_deliberation.simulator import run_deliberation


def test_skeptic_blocks_contradiction():
    result = run_deliberation(
        DeliberationInput(
            topic="candidate promotion",
            evidence_refs=["wiki:a", "wiki:b"],
            contradictions=["relation conflict"],
        )
    )

    assert result.promotion_recommendation == "blocked"
    assert any(statement.role == "skeptic" and statement.blocks_promotion for statement in result.transcript)


def test_privacy_guard_blocks_private_data():
    result = run_deliberation(
        DeliberationInput(
            topic="private fragment",
            evidence_refs=["local:a"],
            privacy_report={"private_data_present": True},
        )
    )

    assert result.promotion_recommendation == "blocked"
    assert any(statement.role == "privacy_guard" and statement.blocks_promotion for statement in result.transcript)


def test_clean_candidate_is_review_only():
    result = run_deliberation(
        DeliberationInput(
            topic="public candidate",
            evidence_refs=["wiki:a", "wiki:b"],
            privacy_report={"private_data_present": False},
            router_report={"route_allowed": True},
        )
    )

    assert result.promotion_recommendation == "approve_for_review"
    assert result.requires_manual_approval is True
    assert result.production_store_mutated is False
    assert result.local_brain_write is False
    assert result.candidate_promotion is False
    assert result.external_llm_used is False
    assert result.real_p2p_used is False


def test_router_blocks_untrusted_route():
    result = run_deliberation(
        DeliberationInput(
            topic="untrusted route",
            evidence_refs=["public:a", "public:b"],
            router_report={"route_allowed": False},
        )
    )

    assert result.promotion_recommendation == "blocked"
    assert any(statement.role == "router" and statement.blocks_promotion for statement in result.transcript)
