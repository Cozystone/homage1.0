from __future__ import annotations

from typing import Any

from .models import ConstructionCandidate


def candidate_to_review_payload(candidate: ConstructionCandidate) -> dict[str, Any]:
    return {
        "title": f"Construction candidate: {candidate.construction_family}",
        "summary": candidate.example_text,
        "item_type": "construction_candidate",
        "candidate_id": candidate.candidate_id,
        "route_type": candidate.route_type,
        "act": candidate.act,
        "source_refs": list(candidate.source_refs),
        "content_hash": candidate.content_hash,
        "scores": {
            "novelty": candidate.novelty_score,
            "usefulness": candidate.usefulness_score,
            "naturalness": candidate.naturalness_score,
            "grounding": candidate.grounding_score,
            "template_risk": candidate.template_risk,
            "safety_risk": candidate.safety_risk,
        },
        "risk_level": "high" if candidate.safety_risk >= 0.5 else "medium" if candidate.template_risk >= 0.5 else "low",
        "suggested_use": "review-only construction retrieval candidate; not production-active",
        "production_active": False,
        "mutation_performed": False,
    }


def export_to_review_queue(candidate: ConstructionCandidate, queue: Any) -> dict[str, Any]:
    item = queue.import_payload("construction_candidate", candidate_to_review_payload(candidate), "construction_bank_v0")
    return item.to_dict()
