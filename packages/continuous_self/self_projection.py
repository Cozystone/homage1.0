# -*- coding: utf-8 -*-
"""SL-1 — project the self onto the SAME representational surface as the world.

SL-0 measured the split (2026-07-28): ATANOR's static identity already lives in the ordinary graph
and the ordinary reasoner reaches it with no self-specific branch, but its LIVE state, history,
capabilities and installation identity sit in four separate JSON/JSONL/dataclass stores that only
dedicated code paths can read. Thirteen self-only branches exist because of that split.

What this module does and, as importantly, does not do:

  * it does NOT move the authoritative stores. They have different consistency, privacy and
    write-authority requirements than a knowledge graph, and SL-0's own conclusion was to keep them
    where they are.
  * it PROJECTS, read-only, the facts those stores already assert into (subject, predicate, object)
    triples — the shape the rest of the engine reasons over.
  * every predicate it emits is checked against `graph_relations()`, the store's own predicate
    column. A predicate the graph does not use is DROPPED rather than invented, because inventing
    one would recreate exactly the hand-table pathology this whole line of work is removing.

Why this is the prerequisite for architecture-level self-deficiency detection, not a separate
feature: the structural-hole detector finds "peers of this type carry relation R, this member does
not". It is domain-blind — it does not know or care that the subjects are countries. Put ATANOR's
own parts on the same surface, with the same predicates, and the SAME organ reads holes in the
architecture. No new detector, nothing hardcoded. That is the whole point: self-knowledge stops
being a special module and becomes an ordinary case of inference.

Read-only by construction: nothing here writes any store, and the shipped graph is opened only to
ask which predicates exist.
"""
from __future__ import annotations

from typing import Any, Iterable

SELF_SUBJECT = "atanor"

# Candidate projections as (predicate, value-extractor). Predicate names are the graph's OWN labels;
# each is dropped at emit time if the store does not actually use it, so this list can never assert a
# relation the engine cannot already reason over.
_PROPERTY_FIELDS = ("mode", "focus", "inquiry_driver")


def _live_predicates() -> frozenset[str]:
    try:
        from packages.base_brain.relational_lookup import graph_relations
        return graph_relations()
    except Exception:                                      # pragma: no cover - store unreadable
        return frozenset()


def _triple(subject: str, predicate: str, obj: Any, allowed: frozenset[str]) -> tuple | None:
    """Emit only when the graph really uses this predicate and the value is a real, non-empty term."""
    if predicate not in allowed:
        return None
    text = str(obj).strip()
    if not text or text.lower() in {"none", "null", "unknown", ""}:
        return None
    return (subject, predicate, text)


def project_state(state: Any, *, allowed: frozenset[str] | None = None) -> list[tuple[str, str, str]]:
    """Triples asserted by a live SelfState. Values are copied verbatim; nothing is derived."""
    allowed = _live_predicates() if allowed is None else allowed
    out: list[tuple[str, str, str]] = []
    for fieldname in _PROPERTY_FIELDS:
        value = getattr(state, fieldname, None)
        t = _triple(SELF_SUBJECT, "has_property", value, allowed)
        if t:
            out.append(t)
    return out


def project_parts(parts: Iterable[str], *, allowed: frozenset[str] | None = None
                  ) -> list[tuple[str, str, str]]:
    """ATANOR's own organs as `has_a` edges — the surface an architecture hole can be read from.

    `parts` is supplied by the caller (a package census, a runtime registry); this module does not
    hardcode a list of organs, because a fixed list is precisely what could never notice a missing
    one."""
    allowed = _live_predicates() if allowed is None else allowed
    out: list[tuple[str, str, str]] = []
    for part in parts:
        t = _triple(SELF_SUBJECT, "has_a", part, allowed)
        if t:
            out.append(t)
    return out


def projection_coverage(state: Any = None, parts: Iterable[str] = ()) -> dict[str, Any]:
    """What the self surface currently supports, and what it drops for lack of a graph predicate.

    A shrinking `dropped` set is the honest measure of SL-1's progress: it is empty exactly when the
    self can be said entirely in the world's own vocabulary."""
    allowed = _live_predicates()
    wanted = {"has_property", "has_a"}
    return {
        "graph_predicates": len(allowed),
        "self_predicates_used": sorted(wanted & allowed),
        "dropped_for_missing_predicate": sorted(wanted - allowed),
        "state_triples": len(project_state(state, allowed=allowed)) if state is not None else 0,
        "part_triples": len(project_parts(parts, allowed=allowed)),
    }
