# -*- coding: utf-8 -*-
"""Grounded metaphor from the continuous phase space (Phase 3-8, Qualia seed 3).

A metaphor is a CROSS-DOMAIN resonance: two concepts far apart in the taxonomy
whose learned phase geometry still vibrates together. The trained phase space
is exactly a continuous representation where that distance exists, so a
metaphor here is MEASURED, never invented:

 metaphor("") -> {"vehicle": "", "resonance": 0.71, ...}

Honesty rules:
 * candidates come only from trained neighbors (no term outside the space)
 * same-family terms are excluded (substring/shared-morpheme — that is not a
 metaphor, it is inflection)
 * directly KG-connected terms are excluded when the store is available (a
 taxonomic relative is a fact, not a metaphor)
 * the sweet band: too-high resonance is a synonym, too-low is noise
"""
from __future__ import annotations

from typing import Any

# the metaphor band: below = unrelated, above = effectively same-domain synonym
_BAND_LO, _BAND_HI = 0.45, 0.92


def _same_family(a: str, b: str) -> bool:
    a, b = a.strip(), b.strip()
    if not a or not b:
        return True
    if a in b or b in a:
        return True

    return len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]


def _kg_connected(a: str, b: str) -> bool:
    try:
        from .answer_bridge import _store

        kg = _store()
        if kg is None:
            return False
        for f in kg.facts_with_sources(a, limit=40) or []:
            if b in (str(f.get("object") or ""), str(f.get("subject") or "")):
                return True
    except Exception:
        pass
    return False


def metaphor(concept: str, k: int = 40) -> dict[str, Any] | None:
    """The best cross-domain resonance for the concept, with its measured basis.
    None when the space doesn't know the concept or nothing sits in the band —
    silence over a forced simile."""
    from .phase_space import neighbors

    cands = neighbors(concept, k=k)
    if not cands:
        return None
    considered = 0
    for term, res in cands:
        if not (_BAND_LO <= res <= _BAND_HI):
            continue
        if _same_family(concept, term):
            continue
        considered += 1
        if considered > 12:  # bound the KG checks
            break
        if _kg_connected(concept, term):
            continue
        return {
            "tenor": concept,
            "vehicle": term,
            "resonance": round(res, 4),
            "surface": f"{concept}은(는) 학습된 위상 기하에서 {term}와(과) 닮은 결로 공명합니다 (공명 {res:.2f}).",
            "basis": "trained_phase_space_cross_domain_resonance",
        }
    return None
