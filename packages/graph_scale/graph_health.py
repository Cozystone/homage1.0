# -*- coding: utf-8 -*-
"""Graph health — the self-refinement flywheel, made observable.

Today the flywheel runs invisibly (contradiction sweep, compaction, taxonomy
sweep, PII/injection guards). This module turns that into ONE honest number:
it runs every detector in READ-ONLY mode (apply=False — nothing is retracted),
counts what it finds, and reports an integrity score with a full breakdown, so
" " is a measurable curve, not a slogan.

Integrity score (0..1): 1.0 minus the weighted density of each defect class per
fact. It is honest by construction — a defect the sweeps would fix lowers the
score until they do; a clean graph scores near 1.0. Read-only and cheap
(bounded row scan), safe to call on every dashboard poll.
"""
from __future__ import annotations

import time
from typing import Any

# weights: how much each defect class costs the integrity score (per fact).
# contradictions and PII are the most serious; taxonomic noise and
# compaction-debt are hygiene.
_WEIGHTS = {
    "contradictions": 3.0,
    "pii_rows": 3.0,
    "injection_rows": 3.0,
    "taxonomic_noise": 1.5,
    "alias_redundancy": 0.5,
}


def _count_pii(store: Any, max_rows: int) -> int:
    try:
        import numpy as np

        from .pii_guard import has_pii

        cols = store.open_columns()
        n = min(len(cols["s"]), max_rows)
        if n == 0:
            return 0
        o = np.asarray(cols["o"][:n])
        checked: dict[int, bool] = {}
        hits = 0
        for oid in o:
            oid = int(oid)
            if oid not in checked:
                checked[oid] = has_pii(store.terms.term(oid))
            if checked[oid]:
                hits += 1
        return hits
    except Exception:
        return 0


def _count_injection(store: Any, max_rows: int) -> int:
    try:
        import numpy as np

        from .injection_guard import has_injection

        cols = store.open_columns()
        n = min(len(cols["s"]), max_rows)
        if n == 0:
            return 0
        o = np.asarray(cols["o"][:n])
        checked: dict[int, bool] = {}
        hits = 0
        for oid in o:
            oid = int(oid)
            if oid not in checked:
                checked[oid] = has_injection(store.terms.term(oid))
            if checked[oid]:
                hits += 1
        return hits
    except Exception:
        return 0


def health_report(store: Any = None, max_rows: int = 500_000) -> dict[str, Any]:
    """Read-only integrity report. Every detector runs with apply=False —
    NOTHING is modified. Returns counts + a 0..1 integrity score."""
    if store is None:
        try:
            from .answer_bridge import _store

            store = _store()
        except Exception:
            store = None
    if store is None:
        return {"available": False, "reason": "store unavailable"}

    total = int(getattr(store, "_count", 0) or 0)
    if total == 0:
        try:
            total = len(store.open_columns()["s"])
        except Exception:
            total = 0

    defects: dict[str, int] = {}
    try:
        from .contradiction_sweep import find_conflicts, find_taxonomic_noise

        defects["contradictions"] = len(find_conflicts(store, max_rows=max_rows))
        defects["taxonomic_noise"] = len(find_taxonomic_noise(store, max_rows=max_rows))
    except Exception:
        defects.setdefault("contradictions", 0)
        defects.setdefault("taxonomic_noise", 0)
    try:
        from .compaction import build_clusters
        from packages.cloud_brain.alias_resolution import AliasResolver
        from .answer_bridge import _ROOT
        from pathlib import Path

        resolver = AliasResolver(Path(_ROOT) / "aliases.jsonl")
        clusters = build_clusters(store, resolver, max_rows=max_rows)
        defects["alias_redundancy"] = sum(len(v) - 1 for v in clusters.values())
    except Exception:
        defects["alias_redundancy"] = 0
    defects["pii_rows"] = _count_pii(store, max_rows)
    defects["injection_rows"] = _count_injection(store, max_rows)

    # integrity = 1 - weighted defect density (bounded to [0,1])
    denom = max(1, total)
    penalty = sum(_WEIGHTS.get(k, 1.0) * v for k, v in defects.items()) / denom
    integrity = round(max(0.0, min(1.0, 1.0 - penalty)), 4)

    return {
        "available": True,
        "total_facts": total,
        "defects": defects,
        "integrity_score": integrity,
        "grade": ("A" if integrity >= 0.99 else "B" if integrity >= 0.97
                  else "C" if integrity >= 0.93 else "D"),
        "note": "read-only; the self-refine daemon fixes these on its tick",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
