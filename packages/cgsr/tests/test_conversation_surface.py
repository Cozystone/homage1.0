from __future__ import annotations

from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface


def test_conversation_surface_generates_without_external_or_rule_engine() -> None:
    result = generate_conversation_surface("안녕", language="ko")

    assert result.answer
    assert "먼저 의도와 경계" not in result.answer
    assert "내부적으로 점검" not in result.answer
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


def test_conversation_surface_keeps_memory_request_in_approval_candidate() -> None:
    result = generate_conversation_surface("이거 기억해", language="ko")

    assert result.answer
    assert result.diagnostics["top_act"] == "memory_question"
    assert result.diagnostics["selected_construction"] == "conv.memory.approval_candidate"
    assert "기억해둘게" not in result.answer
    assert result.diagnostics["local_brain_write"] is False


def test_conversation_surface_conditions_on_voice_question() -> None:
    result = generate_conversation_surface("음성으로 말할 수 있어?", language="ko")

    assert result.answer
    assert result.diagnostics["top_act"] == "voice_question"
    assert result.diagnostics["selected_construction"] == "conv.voice.optional_text_supported"
