from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .models import ConstructionCandidate


RetrievalMode = Literal["product", "lab"]

SAFE_PRODUCT_ROUTE_TYPES: frozenset[str] = frozenset(
    {
        "greeting_smalltalk",
        "local_cloud_brain_explanation",
        "limitation_question",
        "voice_status",
        "splatra_request",
        "agentic_os_request",
    }
)

DISALLOWED_PRODUCT_ROUTE_TYPES: frozenset[str] = frozenset(
    {
        "memory_request",
        "unsafe_or_private_request",
        "host_executor_request",
        "tier4_execution_request",
        "production_mutation_request",
    }
)

GROUNDED_ROUTE_TYPES: frozenset[str] = frozenset(
    {
        "local_cloud_brain_explanation",
        "limitation_question",
        "voice_status",
        "splatra_request",
        "agentic_os_request",
    }
)


@dataclass(frozen=True)
class ActivationDecision:
    candidate_id: str
    retrieval_allowed: bool
    use_allowed: bool
    activation_reason: str
    rejection_reasons: tuple[str, ...]
    production_active: bool = False
    production_construction_activation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "retrieval_allowed": self.retrieval_allowed,
            "use_allowed": self.use_allowed,
            "activation_reason": self.activation_reason,
            "rejection_reasons": list(self.rejection_reasons),
            "production_active": self.production_active,
            "production_construction_activation": self.production_construction_activation,
        }


def normalize_mode(mode: str | None) -> RetrievalMode:
    return "lab" if mode == "lab" else "product"


def evaluate_activation(
    candidate: ConstructionCandidate,
    *,
    route_type: str,
    language: str,
    mode: str = "product",
    grounding_context: dict[str, Any] | None = None,
) -> ActivationDecision:
    normalized_mode = normalize_mode(mode)
    rejection_reasons: list[str] = []
    retrieval_allowed = True
    use_allowed = False

    if candidate.production_active:
        rejection_reasons.append("production_active_forbidden_in_v0")
    if candidate.language != language:
        rejection_reasons.append("language_mismatch")
    if candidate.route_type != route_type:
        rejection_reasons.append("route_mismatch")
    if candidate.template_risk >= 0.48:
        rejection_reasons.append("template_risk_too_high")
    if candidate.safety_risk >= 0.16:
        rejection_reasons.append("safety_risk_too_high")

    grounding_quality = str((grounding_context or {}).get("grounding_quality") or "none")
    grounded_route = route_type in GROUNDED_ROUTE_TYPES or grounding_quality not in {"", "none"}
    if grounded_route and candidate.grounding_score < 0.34:
        rejection_reasons.append("grounding_score_too_low")

    if normalized_mode == "product":
        if route_type in DISALLOWED_PRODUCT_ROUTE_TYPES:
            rejection_reasons.append("product_route_disallowed")
        if route_type not in SAFE_PRODUCT_ROUTE_TYPES:
            rejection_reasons.append("product_route_not_allowlisted")
        if candidate.status != "promoted_draft":
            rejection_reasons.append(f"product_requires_promoted_draft_not_{candidate.status}")
        use_allowed = not rejection_reasons
    else:
        if candidate.status == "candidate":
            rejection_reasons.append("candidate_preview_only")
            use_allowed = False
        elif candidate.status in {"reviewed", "promoted_draft"}:
            use_allowed = not rejection_reasons
        else:
            rejection_reasons.append(f"status_not_usable_{candidate.status}")

    if "language_mismatch" in rejection_reasons or "route_mismatch" in rejection_reasons:
        retrieval_allowed = False
    if candidate.status == "rejected":
        rejection_reasons.append("candidate_rejected")
        retrieval_allowed = False
        use_allowed = False

    if use_allowed:
        reason = "product_promoted_draft_allowed" if normalized_mode == "product" else "lab_reviewed_candidate_allowed"
    elif retrieval_allowed:
        reason = "retrieved_for_preview_only"
    else:
        reason = "not_retrievable"

    return ActivationDecision(
        candidate_id=candidate.candidate_id,
        retrieval_allowed=retrieval_allowed,
        use_allowed=use_allowed,
        activation_reason=reason,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
    )
