"""Construction canonicalization and dedupe for CGSR Stage 1."""

from __future__ import annotations

import hashlib
from typing import Iterable

from .models import ConstructionCandidate


PHRASE_NORMALIZATION = {
    "쉽게 말하": "SIMPLIFY_MARKER",
    "쉽게 말하면": "SIMPLIFY_MARKER",
    "간단히 말하": "SIMPLIFY_MARKER",
    "간단히 말해": "SIMPLIFY_MARKER",
    "쉽게는": "SIMPLIFY_MARKER",
    "핵심은": "KEY_POINT_MARKER",
    "중요한 점은": "KEY_POINT_MARKER",
    "예를 들": "EXAMPLE_MARKER",
    "예를 들어": "EXAMPLE_MARKER",
    "다만": "CAVEAT_MARKER",
    "하지만": "CAVEAT_MARKER",
    "정리하면": "SUMMARY_MARKER",
    "요약하면": "SUMMARY_MARKER",
}

SLOT_TAG_PREFIXES = ("N", "V", "VA", "XR", "SL", "SN")


def normalize_token(token: str) -> str:
    """Normalize a surface token for construction-family matching."""

    folded = (token or "").casefold().strip()
    return PHRASE_NORMALIZATION.get(folded, folded)


def canonicalize(construction: ConstructionCandidate) -> str:
    """Return a canonical form for a construction candidate."""

    pieces: list[str] = []
    for surface, tag, abstract in zip(construction.surface_pattern, construction.tag_pattern, construction.abstract_pattern):
        normalized = normalize_token(surface)
        if normalized in set(PHRASE_NORMALIZATION.values()):
            pieces.append(normalized)
        elif abstract.startswith("SLOT:"):
            pieces.append(abstract)
        elif tag.startswith("J"):
            pieces.append(f"JOSA:{surface}")
        elif tag.startswith("E"):
            pieces.append(f"EOMI:{tag}")
        else:
            pieces.append(normalized)
    return " ".join(pieces)


def family_id(canonical_form: str) -> str:
    """Create a stable construction family id."""

    return "cxf_" + hashlib.sha256(canonical_form.encode("utf-8")).hexdigest()[:16]


def canonical_similarity(a: str, b: str) -> float:
    """Return token-set similarity between canonical forms."""

    aset = set(a.split())
    bset = set(b.split())
    if not aset and not bset:
        return 1.0
    return len(aset & bset) / max(1, len(aset | bset))


def dedupe_constructions(
    candidates: Iterable[ConstructionCandidate],
    *,
    similarity_threshold: float = 0.92,
) -> list[ConstructionCandidate]:
    """Merge near-duplicate construction candidates by canonical form."""

    families: list[ConstructionCandidate] = []
    for candidate in candidates:
        canonical = canonicalize(candidate)
        candidate.canonical_form = canonical
        matched: ConstructionCandidate | None = None
        for family in families:
            if family.canonical_form == canonical or canonical_similarity(family.canonical_form, canonical) >= similarity_threshold:
                matched = family
                break
        if matched is None:
            candidate.family_id = family_id(canonical)
            families.append(candidate)
            continue
        matched.frequency += candidate.frequency
        matched.examples.extend(example for example in candidate.examples if example not in matched.examples)
        matched.examples = matched.examples[:8]
    return families
