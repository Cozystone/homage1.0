# -*- coding: utf-8 -*-
"""Evaluate a Scene against the graph surface — the algebra half of the dynamics layer.

Four operators, closed under composition, all over the interned columns:

    EXTENSION(T)          entities with (x, is_a, T)
    PROJECT(S, p[, o])    members of S carrying (x, p, _) / (x, p, o)
    COMPLEMENT(S, S')     S − S'      <- what "no capital city" actually IS
    readout               set | count | exist | values

Nothing here knows what a country is, or that ATANOR has organs. `EXTENSION("atanor_organ")` and
`EXTENSION("country")` are the same call, which is the whole point: once the census put organs on
the world surface, architecture questions became ordinary scenes and needed no new organ.

HONESTY. A stored graph is not a closed world. `negated=True` can only ever establish "no such
edge in MY graph", never "false in the world", so every negated condition stamps
`closed_world_assumption: True` on the certificate and the caller must not surface it as a
universal claim. Absence over a type whose coverage is near zero is not evidence of anything —
`coverage` is reported so the membrane can refuse a readout resting on it.
"""
from __future__ import annotations

from typing import Any

from packages.scene_model.scene import Condition, Scene


def _cols(store: Any):
    import numpy as np
    c = store.open_columns()
    return np, c["s"], c["p"], c["o"]


def _id(store: Any, term: str) -> int | None:
    try:
        return store.terms.lookup(term)
    except Exception:
        return None


def _is_a_id(store: Any) -> int | None:
    return _id(store, "is_a")


def _cache_for(store: Any, name: str) -> dict | None:
    """A per-STORE cache, held weakly.

    Keyed on the store OBJECT, never on id(store): CPython reuses the id of a freed object, and
    keying on it made one test read another test's cached extension after the first store was
    collected. A stale hit here is silently wrong rather than loud, so the key has to be safe."""
    import weakref
    reg = getattr(_cache_for, "_reg", None)
    if reg is None:
        reg = _cache_for._reg = weakref.WeakKeyDictionary()
    try:
        per = reg.get(store)
        if per is None:
            per = reg[store] = {}
    except TypeError:                                      # not weak-referenceable -> no caching
        return None
    return per.setdefault(name, {})


def _isa_index(store: Any):
    """The `is_a` slice, sorted by object, so a type's extension is a binary-search slice.

    Measured why this exists (2026-07-28): the individual operations were never slow -- one
    `extension()` costs 0.33s, one `project()` 0.32s. What cost 87s on "which cities are located
    in Japan" was calling `extension()` dozens of times while scoring head candidates, each one
    re-scanning 115M rows twice for `(p == is_a) & (o == tid)`. Sorting the is_a slice once turns
    every later extension into a searchsorted slice. Same argsort-groupby shape already used in
    acquisition_daemon/structural_gaps.py.

    Returns None when the store has no `is_a`, so callers fall back to the scan."""
    import numpy as np
    cache = _cache_for(store, "isa_index")
    if cache is None:                                      # unhashable store -> no index, scan
        return None
    if "idx" in cache:
        return cache["idx"]
    np_, s, p, o = _cols(store)
    isa = _is_a_id(store)
    if isa is None:
        cache["idx"] = None
        return None
    rows = p == isa
    s_isa, o_isa = s[rows], o[rows]
    order = np.argsort(o_isa, kind="stable")
    cache["idx"] = (o_isa[order], s_isa[order])
    return cache["idx"]


def extension(store: Any, type_label: str) -> Any:
    """Entities asserted to be of this type. Empty array when the type is unknown."""
    import numpy as np
    cache = _cache_for(store, "extension")
    if cache is not None and type_label in cache:
        return cache[type_label]
    tid = _id(store, type_label)
    if tid is None:
        out = np.zeros(0, dtype="<i4")
    else:
        idx = _isa_index(store)
        if idx is not None:
            o_sorted, s_sorted = idx
            lo, hi = np.searchsorted(o_sorted, [tid, tid + 1])
            out = np.unique(s_sorted[lo:hi])
        else:
            np_, s, p, o = _cols(store)
            isa = _is_a_id(store)
            out = (np.zeros(0, dtype="<i4") if isa is None
                   else np.unique(s[(p == isa) & (o == tid)]))
    if cache is not None:
        cache[type_label] = out
    return out


def _subjects_with(store: Any, predicate: str) -> Any:
    """Every subject carrying this predicate, cached per store.

    Composition scores many (relation, head) pairings and each one was masking a 115M-row column:
    one question took 185s. The subject set per predicate is the reusable part, so it is computed
    once and the pairings become intersections of small arrays."""
    import numpy as np
    cache = _cache_for(store, "subjects")
    if cache is not None and predicate in cache:
        return cache[predicate]
    np_, s, p, o = _cols(store)
    pid = _id(store, predicate)
    out = np.zeros(0, dtype="<i4") if pid is None else np.unique(s[p == pid])
    if cache is not None:
        cache[predicate] = out
    return out


def _intersect_sorted(members: Any, sorted_pool: Any) -> Any:
    """Members present in an already-SORTED pool, by binary search.

    Not `np.intersect1d`: that re-sorts BOTH sides on every call, and the pool here is the cached
    subject set of a predicate -- 9.4M entries for `located_in`. The composer calls project once
    per (span, head, predicate) pairing, so re-sorting 9.4M each time was the real cost of the
    78s "which cities are located in Japan" (the is_a index fixed a different, smaller cost).
    `_subjects_with` returns np.unique output, which is sorted by construction."""
    import numpy as np
    if len(sorted_pool) == 0 or len(members) == 0:
        return np.zeros(0, dtype="<i4")
    pos = np.searchsorted(sorted_pool, members)
    pos = np.minimum(pos, len(sorted_pool) - 1)
    return members[sorted_pool[pos] == members]


def project(store: Any, members: Any, predicate: str, obj: str | None = None) -> Any:
    """Members carrying `predicate` (to `obj` when given). Empty when the predicate is unknown."""
    import numpy as np
    if len(members) == 0 or _id(store, predicate) is None:
        return np.zeros(0, dtype="<i4")
    if obj is None:
        return _intersect_sorted(np.sort(members), _subjects_with(store, predicate))
    np_, s, p, o = _cols(store)
    oid = _id(store, obj)
    if oid is None:
        return np.zeros(0, dtype="<i4")
    return np.intersect1d(members, np.unique(s[(p == _id(store, predicate)) & (o == oid)]),
                          assume_unique=False)


def _labels(store: Any, ids: Any, limit: int) -> list[str]:
    out = []
    for i in ids[:limit]:
        try:
            out.append(store.terms.term(int(i)))
        except Exception:
            continue
    return out


def _norm(label: str) -> str:
    return "".join(ch for ch in label.lower() if ch.isalnum())


def _alias_suspects(store: Any, lacking: Any, having: Any) -> list[str]:
    """Members reported as LACKING a relation that collide, under surface normalization, with a
    member that HAS it.

    Measured on the first real run (2026-07-28): "which countries have no capital city?" returned
    158 of 372, including `france` -- while `France`, a separate interned term in the same
    extension, carries `capital -> Paris`. The split was total: all 214 capital-bearers were
    capitalised, all 140 lowercase members bore none. The graph holds two parallel populations
    (Wikidata entities, ConceptNet concepts) under one type and asserts no identity between them.

    A positive lookup can never expose this -- it finds the bearer and answers. Only the
    complement does. So the complement needs this check, and the check is deliberately a
    SUSPICION that BLOCKS a claim, never one that makes a claim: a false suspicion costs an
    abstention, while a false identity assertion would merge two referents and fabricate. Case is
    not special-cased -- any difference erased by normalization (spacing, punctuation) counts."""
    have_norm = {}
    for i in having:
        try:
            lab = store.terms.term(int(i))
        except Exception:
            continue
        have_norm.setdefault(_norm(lab), lab)
    out = []
    for i in lacking:
        try:
            lab = store.terms.term(int(i))
        except Exception:
            continue
        twin = have_norm.get(_norm(lab))
        if twin is not None and twin != lab:
            out.append(f"{lab}~{twin}")
    return out


def evaluate(scene: Scene, store: Any, *, limit: int = 50) -> dict[str, Any]:
    """Read the scene off the graph, or abstain naming the part that could not be bound."""
    import numpy as np
    bad = scene.well_formed()
    if bad:
        return {"ok": False, "abstain": bad, "certificate": {"derivation_kind": "scene_malformed"}}

    steps: list[str] = []
    closed_world = False

    if scene.entity is not None:
        eid = _id(store, scene.entity)
        if eid is None:
            return {"ok": False, "abstain": f"no grounded record for {scene.entity!r}",
                    "certificate": {"derivation_kind": "scene_unbound_entity"}}
        members = np.array([eid], dtype="<i4")
        steps.append(f"ENTITY({scene.entity})")
        universe = members
    else:
        members = extension(store, scene.var_type)
        steps.append(f"EXTENSION({scene.var_type}) -> {len(members)}")
        if len(members) == 0:
            return {"ok": False, "abstain": f"no members of type {scene.var_type!r} in my graph",
                    "certificate": {"derivation_kind": "scene_empty_extension",
                                    "steps": steps}}
        universe = members

    coverage: dict[str, float] = {}
    suspects: list[str] = []
    for cond in scene.conditions:
        have = project(store, members, cond.predicate, cond.obj)
        cov = (len(project(store, universe, cond.predicate)) / len(universe)) if len(universe) else 0.0
        coverage[cond.predicate] = round(cov, 4)
        if cond.negated:
            closed_world = True
            members = np.setdiff1d(members, have, assume_unique=False)
            steps.append(f"COMPLEMENT({cond.predicate}"
                         + (f"={cond.obj}" if cond.obj else "") + f") -> {len(members)}")
            suspects.extend(_alias_suspects(
                store, members, project(store, universe, cond.predicate)))
        else:
            members = have
            steps.append(f"PROJECT({cond.predicate}"
                         + (f"={cond.obj}" if cond.obj else "") + f") -> {len(members)}")

    cert = {
        "derivation_kind": "scene_evaluation",
        "steps": steps,
        "universe_size": int(len(universe)),
        "relation_coverage": coverage,
        # A negated condition is answered from a graph, which is not a closed world. The caller
        # MUST NOT surface this as "there are none" without saying whose knowledge it is.
        "closed_world_assumption": closed_world,
        # Non-empty => the complement is contaminated by surface-form twins and the membrane must
        # refuse a bare absence claim. Reported, never silently subtracted: dropping them would be
        # this module asserting an identity the graph does not hold.
        "alias_suspects": suspects[:40],
        "alias_suspect_count": len(suspects),
        "guarantees": {"external_llm": False, "fabricated_facts": False},
    }

    if scene.readout == "count":
        return {"ok": True, "count": int(len(members)), "certificate": cert}
    if scene.readout == "exist":
        return {"ok": True, "exists": bool(len(members)), "certificate": cert}
    if scene.readout == "values":
        import numpy as np
        np_, s, p, o = _cols(store)
        pid = _id(store, scene.readout_predicate)
        if pid is None:
            return {"ok": False, "abstain":
                    f"my graph does not use the relation {scene.readout_predicate!r}",
                    "certificate": cert}
        vals = np.unique(o[(p == pid) & np.isin(s, members)])
        return {"ok": True, "values": _labels(store, vals, limit),
                "total": int(len(vals)), "certificate": cert}
    return {"ok": True, "members": _labels(store, members, limit),
            "total": int(len(members)), "certificate": cert}
