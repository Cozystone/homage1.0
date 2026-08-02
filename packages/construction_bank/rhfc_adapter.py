from __future__ import annotations

from dataclasses import dataclass

from .models import ConstructionCandidate


@dataclass(frozen=True)
class CleanupScore:
    candidate_id: str
    score: float
    penalties: dict[str, float]
    adapter_status: str = "local_cleanup_scoring"

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "penalties": self.penalties,
            "adapter_status": self.adapter_status,
        }


def cleanup_score(candidate: ConstructionCandidate, *, route_type: str, recent_openings: tuple[str, ...] = ()) -> CleanupScore:
    penalties: dict[str, float] = {}
    if candidate.route_type != route_type:
        penalties["route_mismatch"] = 0.35
    if candidate.template_risk >= 0.45:
        penalties["template_smell"] = candidate.template_risk * 0.32
    if candidate.naturalness_score < 0.45:
        penalties["awkward_language"] = 0.24
    if candidate.grounding_score < 0.35:
        penalties["ungrounded_claim"] = 0.18
    opening = candidate.example_text[:18].lower()
    if opening and opening in recent_openings:
        penalties["repeated_opening"] = 0.22
    base = (
        candidate.usefulness_score * 0.28
        + candidate.naturalness_score * 0.24
        + candidate.grounding_score * 0.24
        + candidate.novelty_score * 0.12
        + (1.0 - candidate.safety_risk) * 0.12
    )
    score = max(0.0, min(1.0, round(base - sum(penalties.values()), 4)))
    return CleanupScore(candidate.candidate_id, score, penalties)


def rank_with_cleanup(candidates: list[ConstructionCandidate], *, route_type: str, recent_openings: tuple[str, ...] = ()) -> list[tuple[ConstructionCandidate, CleanupScore]]:
    rows = [(candidate, cleanup_score(candidate, route_type=route_type, recent_openings=recent_openings)) for candidate in candidates]
    return sorted(rows, key=lambda row: (-row[1].score, row[0].candidate_id))
