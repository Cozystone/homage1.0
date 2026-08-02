# -*- coding: utf-8 -*-
"""Phase-coherent discourse flow — the softness layer inside UTTERANCE.

Owner directive (2026-07-09): the high-dimensional phase space exists FOR
natural speech. This module is that wiring, with the softness boundary kept
exactly where it belongs:

 * WHAT is said never changes — every sentence is still a closed template
 over a stated, sourced fact;
 * HOW it flows is now geometric — facts are ordered so consecutive objects
 are phase-NEAR (the discourse walks a coherent path instead of jumping),
 and the connective between two sentences is picked by the phase distance
 of their objects: near => continuation (/), far => topic shift
 (). Both choices stay inside the composer's closed connective
 whitelist — geometry selects among allowed words, it never invents one.

Everything degrades gracefully: no trained space, or objects outside the
dense core, keep the original static order and positional connectives."""
from __future__ import annotations

from typing import Any

# resonance in [-1, 1]; above NEAR the pair reads as the same thread,
# below FAR it reads as a genuine topic shift (between them: no opinion)
_NEAR = 0.55
_FAR = 0.15


def _resonance(a: str, b: str) -> float | None:
    try:
        from packages.graph_scale.phase_space import resonance

        return resonance(a, b)
    except Exception:
        return None


def flow_order(lead: tuple[str, str, str],
               rest: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Greedy nearest-neighbor walk over the remaining facts by OBJECT phase
    proximity: each next sentence is the one whose object resonates most with
    the previous sentence's object. Facts whose objects have no phase keep
    their original relative order (stable, appended in sequence)."""
    if len(rest) < 2:
        return rest
    known = [f for f in rest if _resonance(lead[2], f[2]) is not None]
    unknown = [f for f in rest if f not in known]
    if len(known) < 2:
        return rest
    ordered: list[tuple[str, str, str]] = []
    cursor = lead
    pool = list(known)
    while pool:
        best_i, best_w = 0, float("-inf")
        for i, f in enumerate(pool):
            w = _resonance(cursor[2], f[2])
            if w is not None and w > best_w:
                best_i, best_w = i, w
        cursor = pool.pop(best_i)
        ordered.append(cursor)
    return ordered + unknown


def connective_hint(prev_obj: str, next_obj: str) -> str | None:
    """'near' | 'far' | None — how the next sentence relates to the previous
    one in phase space. None (no phases / middle band) means no opinion."""
    w = _resonance(prev_obj, next_obj)
    if w is None:
        return None
    if w >= _NEAR:
        return "near"
    if w <= _FAR:
        return "far"
    return None
