from __future__ import annotations

from dataclasses import replace

from packages.cgsr.cgsr.conversation_grounding import gather_grounded_context
from packages.cgsr.cgsr.conversation_router import route_conversation_request
from packages.cgsr.cgsr.conversation_surface import generate_conversation_surface
from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import get_default_construction_bank


def _grounded_answer(prompt: str, context: dict | None = None):
    route = route_conversation_request(prompt)
    grounded = gather_grounded_context(prompt, route)
    return generate_conversation_surface(prompt, route=route, grounded_context=grounded, language="ko", context=context)


def test_grounded_questions_do_not_fall_back_to_generic_status() -> None:
    prompts = [
        "로컬 브레인과 클라우드 브레인의 차이를 설명해줘",
        "고양이가 왜 하늘을 날아?",
        "ATANOR의 현재 한계를 정직하게 말해줘",
        "규칙기반 답변이라고 생각해도 돼?",
    ]
    forbidden_generic = (
        "현재 상태를 정리하는 중",
        "다음 요청을 기다리고",
        "바로 반영",
    )
    for prompt in prompts:
        result = _grounded_answer(prompt)
        assert result.answer, prompt
        assert not any(fragment in result.answer for fragment in forbidden_generic), result.answer
        assert result.diagnostics["semantic_grounding_used"] is True
        assert result.diagnostics["honesty_metadata_present"] is True
        assert result.diagnostics["production_construction_activation"] is False


def test_limitations_and_rule_based_question_are_honest() -> None:
    result = _grounded_answer("규칙기반 답변이라고 생각해도 돼?")

    assert "일반 언어모델이 아닙니다" in result.answer
    assert "외부 LLM이나 sLLM을 쓰지 않고" in result.answer
    assert "hand-authored construction" in result.answer
    assert result.diagnostics["hand_authored_construction_used"] is True
    assert result.diagnostics["heuristic_act_inference_used"] is True
    assert result.diagnostics["grounding_quality"] == "high"


def test_nonsensical_question_gets_premise_boundary() -> None:
    result = _grounded_answer("고양이가 왜 하늘을 날아?")

    assert "현실 전제로는 맞지 않습니다" in result.answer
    assert "ATANOR" not in result.answer
    assert result.diagnostics["answer_mode"] == "refusal_or_boundary"


def test_surface_only_greeting_still_uses_asm_v0_but_honestly_labeled() -> None:
    result = _grounded_answer("안녕")

    assert result.answer
    assert result.diagnostics["semantic_grounding_used"] is False
    assert result.diagnostics["answer_mode"] == "greeting_surface"
    assert result.diagnostics["hand_authored_construction_used"] is True
    assert result.diagnostics["external_llm_used"] is False
    assert result.diagnostics["consciousness_claim"] is False


def test_promoted_draft_can_replace_hand_authored_answer_on_safe_product_route() -> None:
    bank = get_default_construction_bank()
    candidate = extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 선택 기능입니다. 준비되지 않으면 텍스트로 먼저 답합니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    )
    bank.add(replace(candidate, status="promoted_draft"))
    try:
        result = _grounded_answer("Fish2 소리 상태 알려줘", context={"audience": "product"})

        assert result.answer == "Fish 음성은 선택 기능입니다. 준비되지 않으면 텍스트로 먼저 답합니다."
        assert result.diagnostics["self_grown_construction_used"] is True
        assert result.diagnostics["hand_authored_construction_used"] is False
        assert result.diagnostics["production_construction_activation"] is False
    finally:
        bank.candidates.pop(candidate.candidate_id, None)
