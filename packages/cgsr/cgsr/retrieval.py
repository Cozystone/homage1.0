"""Tiered construction retrieval for CGSR Stage 1.75.

The retriever does not decide factual answer content.  It only selects a
surface construction family that can host a semantic skeleton before the
minimal Korean realizer fills the slots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import ConstructionCandidate


@dataclass(frozen=True)
class RetrievalResult:
    """Result of a construction-bank lookup."""

    tier: str
    matched: bool
    score: float
    reason: str
    construction: ConstructionCandidate | None = None


def _predicate_stem(predicate: str) -> str:
    value = predicate or ""
    for suffix in ("한다", "하다", "준다", "주다", "한다.", "하다."):
        if value.endswith(suffix):
            return value[: -len(suffix)] or value
    return value[:-1] if value.endswith("다") else value


def _row_text(row: ConstructionCandidate) -> str:
    return " ".join(row.surface_pattern + tuple(row.examples) + (row.canonical_form,))


def _structural_score(row: ConstructionCandidate) -> float:
    abstract = list(row.abstract_pattern)
    noun_slots = sum(1 for token in abstract if token == "SLOT:NOUN")
    pred_slots = sum(1 for token in abstract if token == "SLOT:PREDICATE")
    josa = sum(1 for token in row.canonical_form.split() if token.startswith("JOSA:"))
    eomi = sum(1 for token in row.canonical_form.split() if token.startswith("EOMI:"))
    fixed = sum(
        1
        for token in row.canonical_form.split()
        if not token.startswith(("SLOT:", "JOSA:", "EOMI:"))
    )
    return noun_slots * 1.5 + pred_slots * 2.0 + min(josa, 2) * 0.4 + min(eomi, 1) * 0.5 + min(fixed, 4) * 0.15


def _has_predicate_like_shape(row: ConstructionCandidate) -> bool:
    canonical = row.canonical_form.split()
    return (
        "SLOT:PREDICATE" in row.abstract_pattern
        or "하" in canonical
        or any(token.startswith("EOMI:") for token in canonical)
    )


def retrieve_construction(
    skeleton: dict[str, str],
    constructions: Iterable[ConstructionCandidate],
) -> RetrievalResult:
    """Select a construction family by exact, structural, then fallback tiers."""

    rows = list(constructions)
    predicate = skeleton.get("predicate", "")
    stem = _predicate_stem(predicate)
    if stem:
        exact = [row for row in rows if stem in _row_text(row) or predicate in _row_text(row)]
        if exact:
            winner = max(exact, key=lambda row: (row.frequency, _structural_score(row)))
            return RetrievalResult(
                tier="exact",
                matched=True,
                score=float(winner.frequency),
                reason=f"predicate stem '{stem}' found in construction evidence",
                construction=winner,
            )

    structural = [
        row
        for row in rows
        if "SLOT:NOUN" in row.abstract_pattern and _has_predicate_like_shape(row)
    ]
    if structural:
        winner = max(structural, key=lambda row: (_structural_score(row), row.frequency))
        return RetrievalResult(
            tier="structural",
            matched=True,
            score=_structural_score(winner),
            reason="no predicate match; noun/predicate slot structure matched",
            construction=winner,
        )

    return RetrievalResult(
        tier="fallback",
        matched=False,
        score=0.0,
        reason="no exact or structural construction family matched",
    )
