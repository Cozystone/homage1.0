"""Corpus-only self-growth helpers for CGSR construction stores.

The self-growth loop observes a corpus stream, promotes recurrent headed
case-frame constructions, and keeps the evaluation ruler out of every learning
input.  It deliberately builds the same candidate shape consumed by
``rhfc_bridge.store_constructions`` without mutating RHFC internals.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable

from .induction import extract_headed_valency_frames
from .rhfc_bridge import normalize_predicate, predicate_from_canonical
from .storage_policy import GENERIC_PREDICATES


CORE_ROLES = {"SUBJ", "TOPIC"}
DEPENDENT_ROLES = {"OBJ", "ADVL"}


def case_token(role: str, marker: str) -> str:
    """Return the canonical case token used by construction candidates."""

    if role in {"SUBJ", "TOPIC", "OBJ"}:
        return role
    return f"ADVL:{marker}" if role == "ADVL" and marker else role


def canonicalize_growth_frame(cases: tuple[tuple[str, str, str], ...], predicate: str) -> str:
    """Build a deterministic canonical form for a headed valency frame."""

    tokens: list[str] = []
    for role, marker, _ in cases:
        token = case_token(role, marker)
        if token not in tokens:
            tokens.append(token)
    head = next((head for role, _, head in cases if role == "OBJ" and head), "")
    if not head:
        head = next((head for role, _, head in cases if role in CORE_ROLES and head), "")
    if head:
        tokens.append(f"HEAD:{head}")
    normalized_predicate = normalize_predicate(predicate)
    if normalized_predicate:
        tokens.append(f"PREDICATE:{normalized_predicate}")
    return " ".join(tokens)


def frame_is_complete(canonical_form: str) -> bool:
    """Return whether a canonical frame is specific enough for self-growth."""

    tokens = set(str(canonical_form or "").split())
    has_core = bool(tokens & CORE_ROLES)
    has_dependent = bool(tokens & {"OBJ"}) or any(token.startswith("ADVL:") for token in tokens)
    has_predicate = any(token.startswith("PREDICATE:") for token in tokens)
    has_head = any(token.startswith("HEAD:") for token in tokens)
    predicate = predicate_from_canonical(canonical_form)
    return bool(has_core and has_dependent and has_predicate and has_head and predicate not in GENERIC_PREDICATES)


def growth_candidate_id(canonical_form: str) -> str:
    """Return a stable id for a self-grown construction candidate."""

    digest = hashlib.sha256(str(canonical_form).encode("utf-8")).hexdigest()[:16]
    return f"self_growth_cxf_{digest}"


def make_growth_candidate(canonical_form: str, frequency: int, examples: list[str]) -> dict[str, Any]:
    """Create an RHFC-bridge-compatible candidate from a corpus frame."""

    family_id = growth_candidate_id(canonical_form)
    fixed_token_count = len([token for token in canonical_form.split() if not token.startswith("SLOT:")])
    return {
        "family_id": family_id,
        "destination": "rhfc_candidate",
        "priority_score": round(76.0 + min(frequency, 200) * 0.05, 4),
        "reason": "self_growth_stream_case_frame",
        "selection_source": "self_growth_corpus_stream",
        "used_evaluation_cases": False,
        "row": {
            "family_id": family_id,
            "classification": "self_growth_valency_frame",
            "canonical_form": canonical_form,
            "member_count": frequency,
            "reduction_contribution": max(0, frequency - 1),
            "fixed_token_count": fixed_token_count,
            "surface_diversity": 1.0,
            "sample_surfaces": [canonical_form],
            "sample_examples": examples[:3],
        },
    }


def canonical_inventory(candidates: Iterable[dict[str, Any]]) -> set[str]:
    """Return canonical forms already present in a candidate bank."""

    rows = set()
    for item in candidates:
        canonical = str((item.get("row") or {}).get("canonical_form") or "")
        if canonical:
            rows.add(canonical)
    return rows


@dataclass
class SelfGrowthState:
    """Incremental corpus-frame accumulator with explicit promotion control."""

    existing_canonicals: set[str] = field(default_factory=set)
    min_frequency: int = 2
    frame_counts: Counter[str] = field(default_factory=Counter)
    examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    observed_sentences: int = 0
    absorbed_canonicals: set[str] = field(default_factory=set)

    @classmethod
    def from_existing(
        cls,
        candidates: Iterable[dict[str, Any]],
        *,
        min_frequency: int = 2,
    ) -> "SelfGrowthState":
        """Initialize self-growth with a fixed pre-existing candidate bank."""

        return cls(existing_canonicals=canonical_inventory(candidates), min_frequency=min_frequency)

    def observe_batch(self, sentences: Iterable[str], *, max_new: int = 250) -> dict[str, Any]:
        """Observe a corpus batch and propose newly eligible candidates.

        Evaluation cases are intentionally not accepted as an argument here.
        The only input is a sentence stream.
        """

        sentence_rows = list(sentences)
        batch_frames = 0
        for sentence in sentence_rows:
            self.observed_sentences += 1
            for cases, predicate in extract_headed_valency_frames(sentence):
                canonical = canonicalize_growth_frame(cases, predicate)
                if not frame_is_complete(canonical):
                    continue
                self.frame_counts[canonical] += 1
                batch_frames += 1
                if len(self.examples[canonical]) < 3:
                    self.examples[canonical].append(sentence)
        candidates = []
        for canonical, frequency in self.frame_counts.most_common():
            if frequency < self.min_frequency:
                continue
            if canonical in self.existing_canonicals or canonical in self.absorbed_canonicals:
                continue
            candidates.append(make_growth_candidate(canonical, frequency, self.examples.get(canonical, [])))
            if len(candidates) >= max_new:
                break
        return {
            "sentences_seen_in_batch": len(sentence_rows),
            "observed_sentences_total": self.observed_sentences,
            "batch_complete_frames": batch_frames,
            "eligible_new_candidates": candidates,
            "eligible_new_count": len(candidates),
            "eval_rows_used_for_learning": False,
        }

    def accept(self, candidates: Iterable[dict[str, Any]]) -> int:
        """Mark proposed candidates as absorbed after the honesty gate passes."""

        count = 0
        for item in candidates:
            canonical = str((item.get("row") or {}).get("canonical_form") or "")
            if not canonical or canonical in self.absorbed_canonicals:
                continue
            self.absorbed_canonicals.add(canonical)
            count += 1
        return count


def dedupe_candidate_bank(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate a growing candidate bank by canonical form."""

    rows: dict[str, dict[str, Any]] = {}
    for item in candidates:
        canonical = str((item.get("row") or {}).get("canonical_form") or "")
        if canonical and canonical not in rows:
            rows[canonical] = item
    return list(rows.values())
