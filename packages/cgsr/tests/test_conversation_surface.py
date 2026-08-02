from __future__ import annotations

from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface
from packages.cgsr.cgsr.korean_discourse import detect_awkward_korean_markers, score_korean_naturalness


def test_conversation_surface_generates_without_external_or_rule_engine() -> None:
    result = generate_conversation_surface("안녕", language="ko")

    assert result.answer
    assert score_korean_naturalness(result.answer) >= 0.68
    assert not detect_awkward_korean_markers(result.answer)
    assert "먼저 의도와 경계를" not in result.answer
    assert "chain of thought" not in result.answer.lower()
    assert result.diagnostics["generation_basis"] == "local_corpus_construction_transition_model"
    assert result.diagnostics["template_free_surface"] is True
    assert result.diagnostics["external_llm_used"] is False
    assert result.diagnostics["external_sllm_used"] is False
    assert result.diagnostics["rule_based_answer_engine"] is False
    assert result.diagnostics["rule_based_answer_used"] is False
    assert result.diagnostics["local_brain_write"] is False
    assert result.diagnostics["production_store_mutated"] is False
    assert result.diagnostics["candidate_promotion"] is False
    assert result.diagnostics["internal_trace_exposed"] is False


def test_conversation_surface_conditions_on_self_model_construction() -> None:
    result = generate_conversation_surface("지금 자기 모델을 설명해줘", language="ko")

    assert result.answer
    assert result.diagnostics["top_act"] == "self_model_question"
    assert result.diagnostics["selected_construction"] == "conv.self_model.loop"
    assert "진짜 의식" not in result.answer
    assert "AGI" not in result.answer

