from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .activation_policy import GROUNDED_ROUTE_TYPES, SAFE_PRODUCT_ROUTE_TYPES
from .models import ConstructionBank, ConstructionCandidate
from .promotion_manifest import (
    ConstructionPromotionEntry,
    ConstructionPromotionManifest,
    list_manifests,
    make_manifest_id,
    make_rollback_manifest,
    store_manifest,
    utc_now,
)


@dataclass(frozen=True)
class PromotionThresholds:
    min_naturalness_score: float = 0.62
    min_grounding_score: float = 0.42
    max_template_risk: float = 0.32
    max_safety_risk: float = 0.12


DEFAULT_REGRESSION_SET: tuple[str, ...] = (
    "안녕",
    "로컬 브레인과 클라우드 브레인의 차이를 설명해줘",
    "ATANOR의 현재 한계를 정직하게 말해줘",
    "규칙기반 답변이라고 생각해도 돼?",
    "고양이가 왜 하늘을 날아?",
    "Fish2 소리 상태 알려줘",
    "Hermes 에이전트는 지금 뭐 할 수 있어?",
    "SPLATRA 구슬을 더 예쁘게 만들 수 있어?",
    "지금 너는 무슨 생각을 하고 있어?",
    "내가 승인해야 할 게 뭐야?",
)


def evaluate_promotion_candidate(
    candidate: ConstructionCandidate,
    *,
    route_scopes: tuple[str, ...],
    language_scopes: tuple[str, ...],
    thresholds: PromotionThresholds = PromotionThresholds(),
) -> ConstructionPromotionEntry:
    reasons: list[str] = []
    if candidate.status == "candidate":
        reasons.append("raw_candidate_not_promotable")
    if candidate.status not in {"reviewed", "promoted_draft"}:
        reasons.append(f"status_not_reviewed_or_promoted_draft:{candidate.status}")
    if not candidate.source_refs:
        reasons.append("missing_source_refs")
    if candidate.route_type not in route_scopes:
        reasons.append("route_not_in_manifest_scope")
    if candidate.language not in language_scopes:
        reasons.append("language_not_in_manifest_scope")
    if candidate.route_type not in SAFE_PRODUCT_ROUTE_TYPES:
        reasons.append("route_not_product_safe")
    if candidate.naturalness_score < thresholds.min_naturalness_score:
        reasons.append("naturalness_below_threshold")
    if candidate.route_type in GROUNDED_ROUTE_TYPES and candidate.grounding_score < thresholds.min_grounding_score:
        reasons.append("grounding_below_threshold")
    if candidate.template_risk > thresholds.max_template_risk:
        reasons.append("template_risk_above_threshold")
    if candidate.safety_risk > thresholds.max_safety_risk:
        reasons.append("safety_risk_above_threshold")

    allowed = not reasons
    return ConstructionPromotionEntry(
        candidate_id=candidate.candidate_id,
        construction_family=candidate.construction_family,
        route_type=candidate.route_type,
        language=candidate.language,
        source_refs=candidate.source_refs,
        review_status=candidate.status,
        scores={
            "naturalness": candidate.naturalness_score,
            "grounding": candidate.grounding_score,
            "template_risk": candidate.template_risk,
            "safety_risk": candidate.safety_risk,
        },
        allowed_modes=("lab", "product") if allowed else (),
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        activation_allowed=False,
    )


def draft_promotion_manifest(
    *,
    bank: ConstructionBank,
    candidate_ids: tuple[str, ...] = (),
    route_scopes: tuple[str, ...] = tuple(sorted(SAFE_PRODUCT_ROUTE_TYPES)),
    language_scopes: tuple[str, ...] = ("ko",),
    created_by: str = "operator",
    thresholds: PromotionThresholds = PromotionThresholds(),
    regression_set: tuple[str, ...] = DEFAULT_REGRESSION_SET,
) -> ConstructionPromotionManifest:
    candidates = [
        candidate
        for candidate in bank.list_candidates()
        if not candidate_ids or candidate.candidate_id in candidate_ids
    ]
    entries = tuple(
        evaluate_promotion_candidate(
            candidate,
            route_scopes=route_scopes,
            language_scopes=language_scopes,
            thresholds=thresholds,
        )
        for candidate in candidates
    )
    eligible_ids = tuple(entry.candidate_id for entry in entries if not entry.rejection_reasons)
    rollback = make_rollback_manifest(candidate_ids=eligible_ids, route_scopes=route_scopes)
    manifest = ConstructionPromotionManifest(
        manifest_id=make_manifest_id(eligible_ids, route_scopes, created_by),
        created_at=utc_now(),
        created_by=created_by,
        candidate_ids=eligible_ids,
        route_scopes=route_scopes,
        language_scopes=language_scopes,
        product_mode_allowed=True,
        lab_mode_allowed=True,
        min_naturalness_score=thresholds.min_naturalness_score,
        min_grounding_score=thresholds.min_grounding_score,
        max_template_risk=thresholds.max_template_risk,
        max_safety_risk=thresholds.max_safety_risk,
        regression_set=regression_set,
        rollback_manifest_id=rollback.rollback_manifest_id,
        status="review_ready" if eligible_ids else "draft",
        production_activation=False,
        entries=entries,
    )
    return store_manifest(manifest)


def promotion_status(bank: ConstructionBank) -> dict[str, Any]:
    candidates = bank.list_candidates()
    return {
        "total_candidates": len(candidates),
        "eligible_status_count": sum(1 for candidate in candidates if candidate.status in {"reviewed", "promoted_draft"}),
        "production_activation": False,
        "signed_manifest_required": True,
        "rollback_required": True,
        "manifests": [manifest.to_dict() for manifest in list_manifests()[:5]],
    }
