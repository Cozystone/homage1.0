from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from typing import Any, Literal


SourceType = Literal["asm_output", "inner_voice", "web_summary", "review_item", "operator_example", "splatra_brief"]
Language = Literal["ko", "en"]
CandidateStatus = Literal["candidate", "reviewed", "rejected", "promoted_draft"]

INVARIANTS: dict[str, bool] = {
    "external_llm": False,
    "external_sllm": False,
    "local_brain_write": False,
    "production_store_mutated": False,
    "candidate_promotion": False,
    "construction_auto_promoted": False,
    "production_construction_activation": False,
    "signed_manifest_required": True,
    "rollback_required": True,
    "raw_hidden_cot_claim": False,
    "hand_authored_construction_used_disclosed": True,
    "semantic_grounding_metadata_present": True,
    "human_review_required": True,
    "proof_only": True,
}


@dataclass(frozen=True)
class ConstructionCandidate:
    candidate_id: str
    source_type: SourceType
    language: Language
    route_type: str
    act: str
    construction_family: str
    discourse_moves: tuple[str, ...]
    slot_schema: tuple[str, ...]
    lexical_patterns: tuple[str, ...]
    forbidden_phrases: tuple[str, ...]
    example_text: str
    source_refs: tuple[str, ...]
    content_hash: str
    novelty_score: float
    usefulness_score: float
    naturalness_score: float
    grounding_score: float
    template_risk: float
    safety_risk: float
    status: CandidateStatus = "candidate"
    production_active: bool = False

    def __post_init__(self) -> None:
        if self.production_active:
            raise ValueError("construction candidates cannot be production-active in v0")
        for name in (
            "novelty_score",
            "usefulness_score",
            "naturalness_score",
            "grounding_score",
            "template_risk",
            "safety_risk",
        ):
            value = float(getattr(self, name))
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | INVARIANTS.copy()


@dataclass
class ConstructionBank:
    candidates: dict[str, ConstructionCandidate] = field(default_factory=dict)

    def add(self, candidate: ConstructionCandidate) -> ConstructionCandidate:
        existing = self.candidates.get(candidate.candidate_id)
        if existing:
            return existing
        duplicate = self.find_by_hash(candidate.content_hash)
        if duplicate:
            return duplicate
        self.candidates[candidate.candidate_id] = candidate
        return candidate

    def add_many(self, candidates: list[ConstructionCandidate]) -> list[ConstructionCandidate]:
        return [self.add(candidate) for candidate in candidates]

    def find_by_hash(self, content_hash: str) -> ConstructionCandidate | None:
        for candidate in self.candidates.values():
            if candidate.content_hash == content_hash:
                return candidate
        return None

    def list_candidates(self, status: str | None = None) -> list[ConstructionCandidate]:
        values = list(self.candidates.values())
        if status:
            values = [candidate for candidate in values if candidate.status == status]
        return sorted(values, key=lambda item: (-item.usefulness_score, item.template_risk, item.candidate_id))

    def retrieve(self, *, route_type: str, act: str | None = None, language: str = "ko", reviewed_only: bool = True) -> list[ConstructionCandidate]:
        allowed_status = {"reviewed", "promoted_draft"} if reviewed_only else {"candidate", "reviewed", "promoted_draft"}
        scored: list[tuple[float, ConstructionCandidate]] = []
        for candidate in self.candidates.values():
            if candidate.language != language or candidate.status not in allowed_status:
                continue
            score = 0.0
            if candidate.route_type == route_type:
                score += 0.45
            if act and candidate.act == act:
                score += 0.25
            score += candidate.usefulness_score * 0.12
            score += candidate.grounding_score * 0.1
            score += candidate.naturalness_score * 0.08
            score -= candidate.template_risk * 0.18
            score -= candidate.safety_risk * 0.3
            if score > 0.25:
                scored.append((round(score, 4), candidate))
        return [candidate for _, candidate in sorted(scored, key=lambda row: (-row[0], row[1].candidate_id))]

    def mark_status(self, candidate_id: str, status: CandidateStatus) -> ConstructionCandidate:
        current = self.candidates[candidate_id]
        updated = replace(current, status=status, production_active=False)
        self.candidates[candidate_id] = updated
        return updated

    def status(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        by_route: dict[str, int] = {}
        for candidate in self.candidates.values():
            by_status[candidate.status] = by_status.get(candidate.status, 0) + 1
            by_route[candidate.route_type] = by_route.get(candidate.route_type, 0) + 1
        return {
            **INVARIANTS,
            "construction_bank_available": True,
            "total_candidates": len(self.candidates),
            "by_status": by_status,
            "top_route_types": sorted(by_route.items(), key=lambda row: (-row[1], row[0]))[:8],
            "production_active_count": sum(1 for item in self.candidates.values() if item.production_active),
        }

    def export_review_queue_items(self) -> list[dict[str, Any]]:
        from .review_adapter import candidate_to_review_payload

        return [candidate_to_review_payload(candidate) for candidate in self.list_candidates(status="candidate")]


_DEFAULT_BANK = ConstructionBank()


def get_default_construction_bank() -> ConstructionBank:
    return _DEFAULT_BANK


def make_content_hash(parts: list[str]) -> str:
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()
