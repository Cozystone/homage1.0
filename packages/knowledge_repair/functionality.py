# -*- coding: utf-8 -*-
"""Which predicates are single-valued? Derived from the graph, never listed.

A predicate is FUNCTIONAL when the typical subject carrying it carries exactly one value. That is
a distribution the columns already hold, so it does not need to be written down -- and writing it
down was measurably wrong. `truth_maintenance.revision.DEFAULT_FUNCTIONAL` names nine predicates
by hand and includes `located_in`, which the graph scores at 0.825: a city is legitimately
located_in a district AND a country, so treating it as single-valued would flag correct data as
contradictory.

Measured on the shipped graph (fraction of subjects with exactly one value):

    country 0.973   religion 0.969   capital 0.960   sport 0.958   creator 0.928
    is_a 0.833      located_in 0.825  part_of 0.797  occupation 0.695
    has_a 0.390     made_of 0.327     defined_as 0.088

The separation is clean, and it is the graph's own statistic rather than an ontology commitment.
A predicate that becomes multi-valued as knowledge grows re-scores automatically; a hand list
would silently keep asserting the old shape.
"""
from __future__ import annotations

from typing import Any

# A predicate needs enough subjects for its distribution to mean anything. Below this the score is
# noise, so the predicate is simply not classified either way.
MIN_SUBJECTS = 200


def _cache(store: Any, name: str) -> dict | None:
    from packages.scene_model.evaluate import _cache_for
    return _cache_for(store, name)


def functional_scores(store: Any) -> dict[str, float]:
    """predicate -> fraction of its subjects that carry exactly one value.

    Computed once per store; the scan is over the p/s/o columns and is the same argsort-groupby
    shape used elsewhere for per-subject grouping."""
    import numpy as np

    cache = _cache(store, "functional_scores")
    if cache is not None and "scores" in cache:
        return cache["scores"]

    from packages.scene_model.evaluate import _cols
    np_, s, p, o = _cols(store)
    out: dict[str, float] = {}
    for pid in np.unique(p):
        try:
            label = store.terms.term(int(pid))
        except Exception:
            continue
        if not label:
            continue
        m = p == pid
        ss, oo = s[m], o[m]
        if len(ss) < MIN_SUBJECTS:
            continue
        order = np.argsort(ss, kind="stable")
        ss, oo = ss[order], oo[order]
        bounds = np.flatnonzero(np.r_[True, ss[1:] != ss[:-1], True])
        singles = sum(1 for a, b in zip(bounds[:-1], bounds[1:])
                      if len(np.unique(oo[a:b])) == 1)
        out[label] = singles / (len(bounds) - 1)
    if cache is not None:
        cache["scores"] = out
    return out


def functional_predicates(store: Any, *, threshold: float = 0.9) -> frozenset[str]:
    """Predicates single-valued enough that a second value is evidence of a defect.

    The threshold is a dial on how much contradiction evidence to demand, not a fact about the
    world: at 0.9 the shipped graph selects country/religion/capital/sport/creator/manufacturer,
    and excludes `located_in` (0.825), which the hand list wrongly included."""
    return frozenset(k for k, v in functional_scores(store).items() if v >= threshold)
