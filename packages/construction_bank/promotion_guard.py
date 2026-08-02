from __future__ import annotations

from .models import ConstructionCandidate


def assert_no_production_activation(candidate: ConstructionCandidate) -> None:
    if candidate.production_active:
        raise ValueError("construction candidate cannot be production-active in v0")


def promotion_requirements() -> dict[str, object]:
    return {
        "construction_auto_promoted": False,
        "production_construction_activation": False,
        "production_activation_allowed": False,
        "requires_future_signed_manifest": True,
        "requires_operator_approval": True,
        "reviewed_candidates_lab_only": True,
        "hand_authored_construction_dependency_visible": True,
    }


def can_activate_in_production(candidate: ConstructionCandidate) -> bool:
    del candidate
    return False
