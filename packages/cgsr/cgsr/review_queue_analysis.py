"""Analyze CGSR manual-review construction candidates.

The review queue is treated as extraction feedback, not as a place to silently
promote uncertain constructions.  This module groups held-back candidates by
why they failed automatic RHFC storage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any, Iterable


GENERIC_PREDICATES = {
    "하다",
    "되다",
    "있다",
    "없다",
    "대하다",
    "의하다",
    "따르다",
    "위하다",
    "들다",
    "보다",
}


def predicate_from_canonical(canonical_form: str) -> str:
    """Extract the predicate anchor from a canonical valency form."""

    for token in canonical_form.split():
        if token.startswith("PREDICATE:"):
            return token.removeprefix("PREDICATE:")
    return ""


def cluster_review_item(item: dict[str, Any]) -> tuple[str, str]:
    """Return a deterministic review cluster and short explanation."""

    row = item.get("row") or {}
    canonical = str(row.get("canonical_form") or "")
    reason = str(item.get("reason") or "")
    samples = " ".join(row.get("sample_examples") or [])
    predicate = predicate_from_canonical(canonical)
    tokens = set(canonical.split())
    has_advl = any(token.startswith("ADVL:") for token in tokens)
    has_core = bool(tokens & {"SUBJ", "OBJ", "TOPIC"})
    member_count = int(row.get("member_count") or 0)
    if "noise" in reason or re.search(r"\\[a-zA-Z]+|[{}|=]{2,}|::|\\mathbb", samples):
        return "noise_residual", "wiki markup or math-like residue remains"
    if predicate in GENERIC_PREDICATES:
        return "generic_predicate", "predicate is too broad for automatic RHFC storage"
    if not (has_advl and has_core):
        if not has_core:
            return "incomplete_structure", "specific predicate appears, but core argument structure is incomplete"
        if member_count < 8:
            return "frequency_below_auto", "recurrent but below automatic storage frequency"
        return "broad_core_case_frame", "specific predicate but case frame lacks a concrete adverbial/head anchor"
    if member_count < 8:
        return "frequency_below_auto", "recurrent but below automatic storage frequency"
    if "PREDICATE:" not in canonical:
        return "weak_lexical_anchor", "missing predicate lexical anchor"
    return "policy_margin", "near the strict policy boundary but not automatically safe"


def analyze_manual_review_items(items: Iterable[dict[str, Any]], *, examples_per_cluster: int = 5) -> dict[str, Any]:
    """Cluster manual-review items and estimate which ones can be improved."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reasons: dict[str, str] = {}
    for item in items:
        cluster, reason = cluster_review_item(item)
        grouped[cluster].append(item)
        reasons[cluster] = reason
    counts = Counter({key: len(value) for key, value in grouped.items()})
    total = sum(counts.values())
    upgradeable_clusters = {"broad_core_case_frame", "frequency_below_auto", "incomplete_structure"}
    upgradeable = sum(counts.get(key, 0) for key in upgradeable_clusters)
    payload = {
        "total_manual_review": total,
        "cluster_counts": dict(counts.most_common()),
        "upgradeable_estimate": {
            "clusters": sorted(upgradeable_clusters),
            "count": upgradeable,
            "ratio": round(upgradeable / total, 4) if total else 0.0,
            "basis": "These are likely extraction/corpus coverage issues rather than inherently bad constructions.",
        },
        "clusters": {},
    }
    for cluster, rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        payload["clusters"][cluster] = {
            "count": len(rows),
            "reason": reasons[cluster],
            "examples": [
                {
                    "family_id": row.get("family_id"),
                    "priority_score": row.get("priority_score"),
                    "canonical_form": (row.get("row") or {}).get("canonical_form"),
                    "member_count": (row.get("row") or {}).get("member_count"),
                    "sample_examples": ((row.get("row") or {}).get("sample_examples") or [])[:2],
                    "policy_reason": row.get("reason"),
                }
                for row in rows[:examples_per_cluster]
            ],
        }
    return payload
