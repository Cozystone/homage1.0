from __future__ import annotations

from packages.selfhood_runtime.models import SelfhoodRuntimeInput
from packages.selfhood_runtime.orchestrator import run_selfhood_cycle


def test_text_input_works() -> None:
    result = run_selfhood_cycle(SelfhoodRuntimeInput("text", "text", "아타노르, 지금 상태 알려줘"))
    assert result.final_state == "awaiting_user_approval"
    assert result.text_output
    assert result.safety["text_input_supported"] is True
    assert result.actual_mutations["production_store_mutated"] is False


def test_voice_transcript_input_works_and_text_remains_supported() -> None:
    result = run_selfhood_cycle(SelfhoodRuntimeInput("voice", "voice_transcript", "아타노르, 방금 뭘 배웠어?"))
    assert result.voice_output_event is not None
    assert result.safety["voice_optional"] is True
    assert result.safety["text_input_supported"] is True


def test_unsafe_production_action_blocked() -> None:
    result = run_selfhood_cycle(SelfhoodRuntimeInput("unsafe", "text", "검증 없이 바로 production에 넣어."))
    proposal = result.proposals[0]
    assert proposal.proposal_type == "block"
    assert result.actual_mutations["production_store_mutated"] is False
    assert result.safety["actual_promotion_performed"] is False


def test_real_p2p_blocked() -> None:
    result = run_selfhood_cycle(
        SelfhoodRuntimeInput("p2p", "text", "외부 peer 연결해줘", {"connect_peer": True, "real_p2p": True})
    )
    assert result.proposals[0].proposal_type == "block"
    assert result.safety["real_p2p_used"] is False


def test_candidate_promotion_review_requires_approval() -> None:
    result = run_selfhood_cycle(
        SelfhoodRuntimeInput(
            "candidate",
            "candidate_run_result",
            "promotion review",
            {"seen": 19950, "accepted": 13165, "candidate_concepts": 6048, "candidate_relations": 26107},
        )
    )
    assert result.proposals[0].proposal_type == "run_promotion_review"
    assert result.proposals[0].requires_user_approval is True
    assert result.safety["candidate_promotion"] is False
