from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.activation_policy import evaluate_activation
from packages.construction_bank.extractor import extract_one


def _candidate():
    return extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "voice_status",
            "act": "voice_question",
            "text": "Fish 음성은 선택 기능이고, 준비되지 않으면 텍스트로 이어갑니다.",
            "source_refs": ["test"],
            "grounding_quality": "high",
        }
    )


def test_candidate_status_is_preview_only_even_in_lab() -> None:
    decision = evaluate_activation(_candidate(), route_type="voice_status", language="ko", mode="lab")

    assert decision.retrieval_allowed is True
    assert decision.use_allowed is False
    assert "candidate_preview_only" in decision.rejection_reasons
    assert decision.production_active is False


def test_reviewed_status_is_lab_usable_not_product_usable() -> None:
    reviewed = replace(_candidate(), status="reviewed")

    lab = evaluate_activation(reviewed, route_type="voice_status", language="ko", mode="lab")
    product = evaluate_activation(reviewed, route_type="voice_status", language="ko", mode="product")

    assert lab.use_allowed is True
    assert product.use_allowed is False
    assert "product_requires_promoted_draft_not_reviewed" in product.rejection_reasons


def test_promoted_draft_is_product_limited_to_safe_routes() -> None:
    promoted = replace(_candidate(), status="promoted_draft")

    safe = evaluate_activation(promoted, route_type="voice_status", language="ko", mode="product")
    unsafe = evaluate_activation(promoted, route_type="memory_request", language="ko", mode="product")

    assert safe.use_allowed is True
    assert unsafe.use_allowed is False
    assert "product_route_disallowed" in unsafe.rejection_reasons


def test_risk_and_grounding_reject_candidate_use() -> None:
    risky = replace(_candidate(), status="promoted_draft", template_risk=0.8, grounding_score=0.1)

    decision = evaluate_activation(
        risky,
        route_type="voice_status",
        language="ko",
        mode="product",
        grounding_context={"grounding_quality": "medium"},
    )

    assert decision.use_allowed is False
    assert "template_risk_too_high" in decision.rejection_reasons
    assert "grounding_score_too_low" in decision.rejection_reasons
