# -*- coding: utf-8 -*-
"""Sense-disease repair, STAGE 1 — trust filter over hub is_a edges.

Fable5's succession finding: the hub disease is two layers — true polysemy
(a handful of real senses) + PARSE GARBAGE (edges belonging to no sense at
all). Partitioning can only address polysemy; the garbage must be trust-
filtered FIRST. This module is that stage.

The garbage has a MEASURED structural fingerprint (not a word list). On
'capital' all 500 is_a parents were WordNet abstraction ATTRACTORS —
class / position / condition / quality / material / property / process … —
each with is_a in-degree ~30,800–31,100 (one flattening batch dumped the same
abstraction set onto ~31,000 words), and all from the legacy tier. Meanwhile
'Settlement' (in-degree 207k) is a REAL type — but it comes from a REVIEWED
source (dbpedia:bulk), not legacy. So two signals separate garbage from truth:

  source tier   : a reviewed/curated (non-legacy) source is trusted outright;
  discriminativeness : among legacy edges, a parent with modest is_a in-degree
                       is a real type; a high-in-degree generic attractor is
                       the WordNet-batch garbage.

Quarantine is REVERSIBLE (tombstone + ledger) — never column surgery — and
BOUNDED per call, and it runs on hub nodes only (out-degree above a floor).
Answers/definitions are untouched; a hub whose entire is_a set is garbage
falls back to its defined_as edge, which is where its real meaning lives.

STAGES 2–4 (partition survivors → per-sense closure → sense-ID store) build on
a filtered graph; this is the gate they were waiting on."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover
    _HAVE_NP = False

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "trust_quarantine.jsonl"

# measured thresholds (see module docstring for the capital/Settlement calibration)
_GENERIC_INDEGREE = 8_000     # legacy parent above this is a WordNet attractor
_HUB_MIN_PARENTS = 12         # only nodes with this many is_a parents are "hubs"
_LEGACY_TIER = 0              # source id 0 == pre-provenance / bulk-WordNet legacy


def _reviewed_source_ids(store: Any) -> set[int]:
    """Source ids that count as REVIEWED (trusted outright). Everything that is
    not the legacy tier and not a raw scrape carries a name — dbpedia/conceptnet
    bulk, wikidata, curated, type_alignment. Legacy(0) is the untrusted tier."""
    try:
        srcs = store._sources()
        return {i for i, line in enumerate(srcs)
                if i != _LEGACY_TIER and not line.startswith(("web:", "mined:"))}
    except Exception:
        return set()


def _isa_indegree(store: Any) -> dict[int, int]:
    """Global is_a in-degree per object id (cached on the store instance)."""
    cache = getattr(store, "_isa_indegree_cache", None)
    if cache is not None:
        return cache
    root = store.root
    p = np.fromfile(root / "p.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    n = min(len(p), len(o))
    pid = store.terms.lookup("is_a")
    if pid is None:
        return {}
    m = p[:n] == pid
    uo, co = np.unique(o[:n][m], return_counts=True)
    cache = dict(zip(uo.tolist(), co.tolist()))
    store._isa_indegree_cache = cache
    return cache


def edge_trust(store: Any, subject: str) -> list[dict[str, Any]]:
    """Score each of `subject`'s is_a parents: trusted | review | quarantine.
    Uses per-edge source tier + the parent's global is_a in-degree."""
    if not _HAVE_NP:
        return []
    sid = store.terms.lookup(subject)
    if sid is None:
        return []
    root = store.root
    s = np.fromfile(root / "s.col", dtype="<i4")
    p = np.fromfile(root / "p.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    src = np.fromfile(root / "src.col", dtype="<i4")
    n = min(len(s), len(p), len(o), len(src))
    pid = store.terms.lookup("is_a")
    m = (p[:n] == pid) & (s[:n] == sid)
    if not m.any():
        return []
    indeg = _isa_indegree(store)
    reviewed = _reviewed_source_ids(store)
    tomb = store._tombstones()
    rows = [(int(oid), int(srcid)) for oid, srcid in
            zip(o[:n][m].tolist(), src[:n][m].tolist())]
    # HUB CONTEXT is load-bearing: a high-in-degree parent is GARBAGE on a hub
    # (capital is_a Animal — part of the WordNet attractor batch) but the REAL

    # generic-attractor quarantine therefore fires only when the node is a hub.
    is_hub = len({oid for oid, _ in rows}) >= _HUB_MIN_PARENTS
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for oid, srcid in rows:
        parent = store.terms.term(oid)
        if not parent or parent in seen or (subject, "is_a", parent) in tomb:
            continue
        seen.add(parent)
        d = int(indeg.get(oid, 0))
        if srcid in reviewed:
            verdict = "trusted"                       # a reviewed source vouches
        elif is_hub and d >= _GENERIC_INDEGREE:
            verdict = "quarantine"                    # hub + generic attractor = batch garbage
        elif is_hub and d >= _GENERIC_INDEGREE // 4:
            verdict = "review"
        else:
            verdict = "trusted"                       # non-hub, or discriminative type
        out.append({"parent": parent, "source_id": srcid,
                    "in_degree": d, "verdict": verdict})
    return sorted(out, key=lambda r: -r["in_degree"])


def trusted_parents(store: Any, subject: str) -> list[str]:
    """READ-TIME consumer API (the safe way to apply stage 1 at scale): the
    subject's is_a parents with the garbage batch removed, no store writes and
    no tombstone burden. sense_partition / answers call this instead of raw
    facts_about so the hub disease never reaches a reading. Physical removal
    (stage 4 store migration) stays a separate, operator-gated step."""
    return [e["parent"] for e in edge_trust(store, subject)
            if e["verdict"] != "quarantine"]


def trust_report(store: Any, subject: str) -> dict[str, Any]:
    """Non-destructive: how much of this hub's is_a set is trustworthy?"""
    edges = edge_trust(store, subject)
    from collections import Counter
    v = Counter(e["verdict"] for e in edges)
    return {
        "subject": subject, "parents": len(edges),
        "trusted": v["trusted"], "review": v["review"], "quarantine": v["quarantine"],
        "is_hub": len(edges) >= _HUB_MIN_PARENTS,
        "quarantine_sample": [e["parent"] for e in edges if e["verdict"] == "quarantine"][:8],
        "trusted_sample": [e["parent"] for e in edges if e["verdict"] == "trusted"][:8],
    }


def quarantine_hub(store: Any, subject: str, *, apply: bool = False,
                   max_retract: int = 400) -> dict[str, Any]:
    """Quarantine the garbage is_a edges of ONE hub (reversible tombstone).
    apply=False reports only. Bounded; hubs only; never touches non-is_a edges.
    A subject keeps at least its trusted parents — if the whole set is garbage
    the answer path already prefers defined_as, so removal is safe."""
    edges = edge_trust(store, subject)
    if len(edges) < _HUB_MIN_PARENTS:
        return {"subject": subject, "skipped": "not_a_hub", "parents": len(edges)}
    targets = [e for e in edges if e["verdict"] == "quarantine"][:max_retract]
    removed = 0
    if apply:
        for e in targets:
            try:
                store.retract(subject, "is_a", e["parent"], reason="hub_trust_quarantine")
                removed += 1
            except Exception:
                continue
        if targets:
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "subject": subject, "quarantined": removed,
                                     "parents": [t["parent"] for t in targets[:50]]},
                                    ensure_ascii=False) + "\n")
    return {"subject": subject, "parents": len(edges),
            "quarantine_candidates": len(targets),
            "quarantined": removed if apply else 0, "applied": apply,
            "kept_trusted": sum(1 for e in edges if e["verdict"] == "trusted")}


def find_hubs(store: Any, *, min_parents: int = _HUB_MIN_PARENTS,
              max_hubs: int = 5000) -> list[str]:
    """Subjects whose is_a out-degree makes them polysemy/garbage hubs — the
    working set for the trust filter (measured live: ~32k such nodes, 0.45%)."""
    if not _HAVE_NP:
        return []
    root = store.root
    s = np.fromfile(root / "s.col", dtype="<i4")
    p = np.fromfile(root / "p.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    n = min(len(s), len(p), len(o))
    pid = store.terms.lookup("is_a")
    if pid is None:
        return []
    m = p[:n] == pid
    ss, oo = s[:n][m], o[:n][m]
    key = (ss.astype(np.int64) << 32) | (oo.astype(np.int64) & 0xFFFFFFFF)
    key = np.unique(key)
    subj = (key >> 32).astype(np.int64)
    usubj, cnt = np.unique(subj, return_counts=True)
    hubs = usubj[cnt >= min_parents]
    order = np.argsort(-cnt[cnt >= min_parents])
    return [store.terms.term(int(hubs[i])) for i in order[:max_hubs]]
