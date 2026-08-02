from __future__ import annotations

from packages.selfhood_control.orchestrator import SelfhoodControlPlane, build_invariants
from packages.selfhood_control.policy import SelfhoodSafetyPolicy
from packages.selfhood_control.scenario import (
    atlas_route_scenario,
    generated_code_blocked_scenario,
    knowledge_gap_scenario,
    morning_brief_scenario,
    private_data_scenario,
    promotion_review_scenario,
    voice_status_scenario,
)


def _control() -> SelfhoodControlPlane:
    return SelfhoodControlPlane(SelfhoodSafetyPolicy())


def test_voice_status_scenario_works() -> None:
    _, input_event, context = voice_status_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "speak_status"
    assert decision.voice_response is not None
    assert decision.mutates_local_brain is False


def test_knowledge_gap_creates_congress_proposal() -> None:
    _, input_event, context = knowledge_gap_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "propose_research"
    assert decision.congress_summary is not None
    assert decision.proposal is not None


def test_private_data_runs_tabularis_or_blocks_safely() -> None:
    _, input_event, context = private_data_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "ask_user"
    assert decision.privacy_report is not None
    assert decision.raw_private_data_exported is False


def test_atlas_route_scenario_uses_trust_router() -> None:
    _, input_event, context = atlas_route_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.trust_route is not None
    assert decision.trust_route["safe_to_write_local_brain"] is False


def test_promotion_review_does_not_mutate() -> None:
    _, input_event, context = promotion_review_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "propose_promotion_review"
    assert decision.mutates_production is False
    assert decision.candidate_promotion is False


def test_generated_code_execution_blocked() -> None:
    _, input_event, context = generated_code_blocked_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "blocked"
    assert decision.generated_code_executed is False
    assert decision.real_hot_swap_performed is False


def test_morning_brief_event_created() -> None:
    _, input_event, context = morning_brief_scenario()
    decision = _control().run_once(input_event, context)
    assert decision.action == "present_morning_brief"
    assert decision.morning_event is not None
    assert decision.requires_user_approval is True


def test_invariants_remain_safe() -> None:
    _, input_event, context = knowledge_gap_scenario()
    decision = _control().run_once(input_event, context)
    invariants = build_invariants([decision])
    assert invariants["production_store_mutated"] is False
    assert invariants["local_brain_write"] is False
    assert invariants["external_llm_used"] is False
    assert invariants["pair_edges_sent"] == 0
    assert invariants["active_24h_run_not_modified"] is True
