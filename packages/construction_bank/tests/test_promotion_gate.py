from __future__ import annotations

from dataclasses import replace

from packages.construction_bank.extractor import extract_one
from packages.construction_bank.models import ConstructionBank
from packages.construction_bank.promotion_gate import draft_promotion_manifest, evaluate_promotion_candidate, promotion_status


def _base_candidate():
    return extract_one(
        {
            "source_type": "operator_example",
            "language": "ko",
            "route_type": "splatra_request",
            "act": "visual_request",
            "text": "SPLATRA 구슬은 검증된 상태에서만 시각 후보로 보여주고, 실제 적용은 리뷰 뒤에 진행합니다.",
            "source_refs": ["unit-test"],
            "grounding_quality": "high",
        }
    )


def test_risky_reviewed_candidate_is_rejected_without_activation() -> None:
    candidate = replace(
        _base_candidate(),
        status="reviewed",
        template_risk=0.91,
        safety_risk=0.3,
        grounding_score=0.1,
    )

    entry = evaluate_promotion_candidate(candidate, route_scopes=("splatra_request",), language_scopes=("ko",))

    assert entry.activation_allowed is False
    assert "template_risk_above_threshold" in entry.rejection_reasons
    assert "safety_risk_above_threshold" in entry.rejection_reasons
    assert "grounding_below_threshold" in entry.rejection_reasons


def test_promotion_status_lists_recent_manifest_without_store_mutation() -> None:
    bank = ConstructionBank()
    candidate = bank.add(replace(_base_candidate(), status="reviewed"))
    draft_promotion_manifest(bank=bank, candidate_ids=(candidate.candidate_id,))

    status = promotion_status(bank)

    assert status["total_candidates"] == 1
    assert status["eligible_status_count"] == 1
    assert status["production_activation"] is False
    assert status["signed_manifest_required"] is True
    assert status["rollback_required"] is True
    assert status["manifests"]

