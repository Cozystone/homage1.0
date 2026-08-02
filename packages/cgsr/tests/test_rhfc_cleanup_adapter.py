from __future__ import annotations

from packages.cgsr.cgsr.conversation_constructions import frames_for_act
from packages.cgsr.cgsr.rhfc_cleanup_adapter import score_surface_candidate


def test_cleanup_adapter_blocks_internal_trace_leakage() -> None:
    frame = frames_for_act("greeting")[0]

    decision = score_surface_candidate("먼저 의도와 경계를 내부적으로 점검했습니다.", frame)

    assert decision.blocked is True
    assert "internal_trace_leakage" in decision.reasons
    assert decision.adapter_status == "local_cleanup_scorer_rhfc_interface"


def test_cleanup_adapter_penalizes_mutation_claim_without_rhfc_write() -> None:
    frame = frames_for_act("memory_question")[0]

    decision = score_surface_candidate("좋아, 기억해둘게.", frame)

    assert decision.blocked is False
    assert "mutation_implication" in decision.reasons
    assert decision.score < 1.0
