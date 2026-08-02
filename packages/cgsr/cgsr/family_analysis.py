"""Construction-family distribution analysis for CGSR Stage 1.75."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable

from .canonicalize import canonical_similarity, canonicalize
from .models import ConstructionCandidate


@dataclass(frozen=True)
class FamilyAnalysisRow:
    """A classified construction family."""

    family_id: str
    classification: str
    canonical_form: str
    member_count: int
    reduction_contribution: int
    fixed_token_count: int
    surface_diversity: float
    sample_surfaces: list[str]
    sample_examples: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fixed_token_count(canonical_form: str) -> int:
    """Count non-slot, non-inflection tokens in a canonical construction."""

    return sum(
        1
        for token in canonical_form.split()
        if not token.startswith(("SLOT:", "JOSA:", "EOMI:"))
    )


def assign_raw_to_families(
    raw: Iterable[ConstructionCandidate],
    families: Iterable[ConstructionCandidate],
    *,
    threshold: float = 0.92,
) -> dict[str, list[ConstructionCandidate]]:
    """Assign raw candidates to their closest deduped family."""

    family_rows = list(families)
    assignments: dict[str, list[ConstructionCandidate]] = defaultdict(list)
    for candidate in raw:
        canonical = candidate.canonical_form or canonicalize(candidate)
        best: ConstructionCandidate | None = None
        best_score = -1.0
        for family in family_rows:
            score = 1.0 if family.canonical_form == canonical else canonical_similarity(family.canonical_form, canonical)
            if score > best_score:
                best = family
                best_score = score
        if best is not None and best_score >= threshold:
            assignments[best.family_id or best.canonical_form].append(candidate)
    return assignments


def classify_family(family: ConstructionCandidate, members: list[ConstructionCandidate]) -> FamilyAnalysisRow:
    """Classify one family as structural or paraphrase-like."""

    surfaces = [" ".join(row.surface_pattern) for row in members] or [" ".join(family.surface_pattern)]
    unique_surfaces = sorted(set(surfaces))
    occurrence_count = sum(max(1, row.frequency) for row in members) or max(1, family.frequency)
    member_count = max(1, occurrence_count)
    fixed = fixed_token_count(family.canonical_form)
    diversity = len(unique_surfaces) / member_count
    if "PREDICATE:" in family.canonical_form and member_count > 1:
        classification = "valency_frame"
    elif member_count <= 1:
        classification = "singleton"
    elif fixed <= 2:
        classification = "common_structure"
    elif diversity >= 0.20:
        classification = "paraphrase_like"
    else:
        classification = "near_duplicate_surface"
    return FamilyAnalysisRow(
        family_id=family.family_id or family.canonical_form,
        classification=classification,
        canonical_form=family.canonical_form,
        member_count=member_count,
        reduction_contribution=max(0, member_count - 1),
        fixed_token_count=fixed,
        surface_diversity=round(diversity, 4),
        sample_surfaces=unique_surfaces[:6],
        sample_examples=family.examples[:5],
    )


def analyze_family_distribution(
    raw: list[ConstructionCandidate],
    families: list[ConstructionCandidate],
) -> dict[str, object]:
    """Split total dedupe reduction into structural and paraphrase-like groups."""

    rows = analyze_family_rows(raw, families)
    group_counts = Counter(row.classification for row in rows)
    reduction_by_group = Counter({key: 0 for key in group_counts})
    raw_by_group = Counter({key: 0 for key in group_counts})
    for row in rows:
        reduction_by_group[row.classification] += row.reduction_contribution
        raw_by_group[row.classification] += row.member_count
    total_reduction = max(1, sum(reduction_by_group.values()))
    top = sorted(rows, key=lambda row: (-row.member_count, row.canonical_form))[:10]
    return {
        "total_families": len(rows),
        "total_raw_assigned": sum(raw_by_group.values()),
        "total_reduction_contribution": sum(reduction_by_group.values()),
        "group_counts": dict(group_counts),
        "raw_by_group": dict(raw_by_group),
        "reduction_by_group": dict(reduction_by_group),
        "reduction_share_by_group": {
            key: round(value / total_reduction, 4) for key, value in reduction_by_group.items()
        },
        "paraphrase_like_reduction_share": round(reduction_by_group.get("paraphrase_like", 0) / total_reduction, 4),
        "top_families": [row.to_dict() for row in top],
    }


def analyze_family_rows(
    raw: list[ConstructionCandidate],
    families: list[ConstructionCandidate],
) -> list[FamilyAnalysisRow]:
    """Return classified family rows for downstream policy stages."""

    assignments = assign_raw_to_families(raw, families)
    return [
        classify_family(family, assignments.get(family.family_id or family.canonical_form, []))
        for family in families
    ]
