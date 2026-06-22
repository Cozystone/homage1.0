from __future__ import annotations

from packages.cgsr.cgsr.asm_v0 import (
    ASM_GENERATION_BASIS,
    generate_surface,
    infer_conversation_act,
    result_to_public_diagnostics,
)


def test_infer_conversation_act_is_distribution_not_answer_router() -> None:
    distribution = infer_conversation_act("오늘 브리프 보여줘")

    assert distribution.top_act() == "brief_request"
    assert abs(sum(distribution.probabilities.values()) - 1.0) < 0.00001
    assert "answer" not in distribution.features


def test_generate_surface_returns_construction_conditioned_candidate() -> None:
    result = generate_surface("뭐 하고 있어?")

    assert result.answer
    assert result.generation_basis == ASM_GENERATION_BASIS
    assert result.selected_construction == "conv.status.present_activity"
    assert result.safety_flags["external_llm"] is False
    assert result.safety_flags["external_sllm"] is False
    assert result.safety_flags["rule_based_answer_used"] is False
    assert result.safety_flags["template_free_surface"] is True
    assert result.safety_flags["production_store_mutated"] is False
    assert result.internal_trace_exposed is False


def test_public_diagnostics_hide_candidate_text_and_trace() -> None:
    result = generate_surface("안녕")
    diagnostics = result_to_public_diagnostics(result)

    assert diagnostics["generation_basis"] == ASM_GENERATION_BASIS
    assert diagnostics["candidates_hidden"] is True
    assert "candidates" not in diagnostics
    assert diagnostics["internal_trace_exposed"] is False
