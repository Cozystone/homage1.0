"""Corpus-statistical predicate coverage policy for CGSR Stage 2.6.

This module is deliberately separated from the Stage 2.4 fixture-derived
coverage track.  It never accepts evaluation-case rows.  Its only inputs are
corpus sentences and the already strict RHFC candidate list, so any candidate it
adds is reviewable corpus evidence rather than benchmark leakage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any, Iterable

from .induction import extract_headed_valency_frames
from .rhfc_bridge import normalize_predicate
from .storage_policy import GENERIC_PREDICATES


def predicate_from_canonical(canonical_form: str) -> str:
    """Extract a normalized predicate token from a canonical construction."""

    for token in str(canonical_form or "").split():
        if token.startswith("PREDICATE:"):
            return normalize_predicate(token.removeprefix("PREDICATE:"))
    return ""


def strict_predicate_inventory(candidates: Iterable[dict[str, Any]]) -> set[str]:
    """Return normalized predicate coverage from strict RHFC candidates."""

    predicates: set[str] = set()
    for item in candidates:
        canonical = str((item.get("row") or {}).get("canonical_form") or "")
        predicate = predicate_from_canonical(canonical)
        if predicate:
            predicates.add(predicate)
    return predicates


def _case_token(role: str, marker: str, head: str) -> str:
    if role in {"SUBJ", "TOPIC", "OBJ"}:
        return role
    if marker:
        return f"{role}:{marker}"
    return role


def _frame_canonical(cases: tuple[tuple[str, str, str], ...], predicate: str) -> str:
    tokens = [_case_token(role, marker, head) for role, marker, head in cases]
    head = next((head for role, _, head in cases if role == "OBJ" and head), "")
    if not head:
        head = next((head for role, _, head in cases if role in {"TOPIC", "SUBJ"} and head), "")
    if head:
        tokens.append(f"HEAD:{head}")
    tokens.append(f"PREDICATE:{predicate}")
    return " ".join(tokens)


def collect_corpus_predicate_stats(sentences: Iterable[str]) -> dict[str, Any]:
    """Collect predicate frequencies and representative valency frames.

    The function only reads corpus sentences.  It intentionally has no
    parameter for evaluation cases, which is the Stage 2.6 leakage guard.
    """

    predicate_counts: Counter[str] = Counter()
    frame_counts: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)
    for sentence in sentences:
        for cases, raw_predicate in extract_headed_valency_frames(sentence):
            predicate = normalize_predicate(raw_predicate)
            if not predicate:
                continue
            canonical = _frame_canonical(cases, predicate)
            predicate_counts[predicate] += 1
            frame_counts[predicate][canonical] += 1
            if len(examples[canonical]) < 3:
                examples[canonical].append(sentence)
    return {
        "predicate_counts": dict(predicate_counts),
        "frame_counts": {predicate: dict(counts) for predicate, counts in frame_counts.items()},
        "examples": dict(examples),
    }


def _frequency_threshold(counts: list[int], percentile: float) -> int:
    if not counts:
        return 0
    ordered = sorted(counts)
    clamped = min(0.99, max(0.0, percentile))
    index = int(round((len(ordered) - 1) * clamped))
    return max(1, ordered[index])


def _candidate_id(predicate: str, canonical_form: str) -> str:
    payload = f"{predicate}|{canonical_form}"
    return "corpus_cxf_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _make_candidate(predicate: str, canonical_form: str, frequency: int, examples: list[str]) -> dict[str, Any]:
    family_id = _candidate_id(predicate, canonical_form)
    fixed_token_count = len([token for token in canonical_form.split() if not token.startswith("SLOT:")])
    return {
        "family_id": family_id,
        "destination": "rhfc_candidate",
        "priority_score": round(72.0 + min(frequency, 200) * 0.05, 4),
        "reason": "corpus_statistical_track, corpus_wide_frequency",
        "selection_source": "corpus_statistical_track",
        "used_evaluation_cases": False,
        "row": {
            "family_id": family_id,
            "classification": "corpus_statistical_valency_frame",
            "canonical_form": canonical_form,
            "member_count": frequency,
            "reduction_contribution": max(0, frequency - 1),
            "fixed_token_count": fixed_token_count,
            "surface_diversity": 1.0,
            "sample_surfaces": [canonical_form],
            "sample_examples": examples[:3],
        },
    }


def build_corpus_statistical_track(
    sentences: Iterable[str],
    strict_candidates: list[dict[str, Any]],
    *,
    percentile: float = 0.70,
    max_predicates: int = 40,
    include_generic: bool = False,
) -> dict[str, Any]:
    """Build a corpus-derived coverage track without reading evaluation rows."""

    sentence_rows = list(sentences)
    stats = collect_corpus_predicate_stats(sentence_rows)
    predicate_counts = Counter(stats["predicate_counts"])
    strict_predicates = strict_predicate_inventory(strict_candidates)
    threshold = _frequency_threshold(list(predicate_counts.values()), percentile)
    rows = []
    for predicate, frequency in predicate_counts.most_common():
        normalized = normalize_predicate(predicate)
        if not normalized or normalized in strict_predicates:
            continue
        if not include_generic and normalized in GENERIC_PREDICATES:
            continue
        if frequency < threshold:
            continue
        frame_counter = Counter(stats["frame_counts"].get(predicate, {}))
        if not frame_counter:
            continue
        canonical_form, _ = frame_counter.most_common(1)[0]
        rows.append(_make_candidate(normalized, canonical_form, frequency, stats["examples"].get(canonical_form, [])))
        if len(rows) >= max_predicates:
            break
    return {
        "track_name": "corpus_statistical_track",
        "sentences_seen": len(sentence_rows),
        "unique_predicates": len(predicate_counts),
        "frequency_percentile": percentile,
        "frequency_threshold": threshold,
        "strict_predicate_count": len(strict_predicates),
        "candidate_count": len(rows),
        "predicate_list": [
            predicate_from_canonical(item["row"]["canonical_form"])
            for item in rows
        ],
        "candidates": rows,
        "leakage_review": {
            "uses_evaluation_cases": False,
            "builder_inputs": ["corpus_sentences", "strict_candidates"],
            "evaluation_case_rows_parameter_exists": False,
            "domain_fixture_track_used": False,
        },
    }
