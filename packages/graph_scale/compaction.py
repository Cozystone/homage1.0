# -*- coding: utf-8 -*-
"""Knowledge compaction — self-refinement stage 2, the SOUND form.

Gemini's stage 2 (" ") is right in spirit but dangerous if taken as
"merge similar concepts" — that destroys real distinctions (= vs
= must NOT merge; sense_split argues for SPLITTING those). The only
compaction that loses NO information is merging surface forms that are provably
the SAME entity: / Nvidia / . That redundancy is
pure bloat, and collapsing it genuinely shrinks the graph.

The discipline (why this is safe):
 * merges come ONLY from the alias resolver, which learned each pair from real
 evidence (" (Nvidia Corporation)…") or curated pairs —
 NEVER from mere embedding similarity (that is the distinction-losing trap).
 * the canonical surface form is the cluster member the graph references MOST
 (authority by usage), tie-broken by a Korean-preference then length.
 * rewriting is tombstone-old + add-canonical, so it is reversible and audited
 like every other retraction; the store's exact de-dup collapses the
 now-identical triples.

Result: fewer nodes, identical knowledge, and every downstream answer resolves
variant spellings to one concept. Stage 2 completes the self-refine flywheel.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "compaction.jsonl"


def _has_hangul(s: str) -> bool:
    return any("가" <= c <= "힣" for c in s)


def build_clusters(store: Any, resolver: Any, max_rows: int = 2_000_000) -> dict[str, list[str]]:
    """Group the store's SURFACE terms by their alias-resolver representative.
    Only clusters with >= 2 distinct surface forms are returned (the rest are
    already singletons — nothing to compact)."""
    import numpy as np

    cols = store.open_columns()
    n = min(len(cols["s"]), max_rows)
    if n == 0:
        return {}
    # every distinct term id that appears as a subject or object
    ids = np.unique(np.concatenate([np.asarray(cols["s"][:n]), np.asarray(cols["o"][:n])]))
    groups: dict[str, set[str]] = defaultdict(set)
    for tid in ids:
        term = store.terms.term(int(tid))
        if not term:
            continue
        rep = resolver.resolve(term)
        groups[rep].add(term)
    return {rep: sorted(forms) for rep, forms in groups.items() if len(forms) > 1}


def _canonical(forms: list[str], usage: Counter) -> str:
    """The surface form the graph references most (authority by usage);
 tie-break: Korean preferred, then the SHORTER common name ( over
 — the everyday name, not the legal one)."""
    return max(forms, key=lambda f: (usage.get(f, 0), _has_hangul(f), -len(f)))


def compact(store: Any, resolver: Any = None, *, apply: bool = False,
            max_rows: int = 2_000_000) -> dict[str, Any]:
    """Rewrite alias-variant triples to their canonical surface form. Returns
    measured counts; every rewrite is tombstone-old + add-canonical (reversible,
    audited). No resolver -> nothing to do (never merges on guesswork)."""
    import numpy as np

    if resolver is None:
        try:
            from packages.cloud_brain.alias_resolution import AliasResolver
            from .answer_bridge import _ROOT

            resolver = AliasResolver(Path(_ROOT) / "aliases.jsonl")
        except Exception:
            return {"clusters": 0, "rewritten": 0, "nodes_merged": 0}

    clusters = build_clusters(store, resolver, max_rows=max_rows)
    if not clusters:
        return {"clusters": 0, "rewritten": 0, "nodes_merged": 0}

    cols = store.open_columns()
    n = min(len(cols["s"]), max_rows)
    s_col = np.asarray(cols["s"][:n])
    o_col = np.asarray(cols["o"][:n])
    p_col = np.asarray(cols["p"][:n])
    # usage = how often each surface term is referenced (authority signal)
    usage: Counter = Counter()
    for tid in np.concatenate([s_col, o_col]):
        usage[store.terms.term(int(tid))] += 1

    # map every non-canonical surface form -> its canonical form
    remap: dict[str, str] = {}
    merged_nodes = 0
    canon_ledger = []
    for rep, forms in clusters.items():
        canon = _canonical(forms, usage)
        variants = [f for f in forms if f != canon]
        if not variants:
            continue
        merged_nodes += len(variants)
        canon_ledger.append({"canonical": canon, "variants": variants})
        for v in variants:
            remap[v] = canon
    if not remap:
        return {"clusters": len(clusters), "rewritten": 0, "nodes_merged": 0}

    tomb = store._tombstones()
    rewritten = 0
    if apply:
        for i in range(n):
            subj = store.terms.term(int(s_col[i]))
            pred = store.terms.term(int(p_col[i]))
            obj = store.terms.term(int(o_col[i]))
            if (subj, pred, obj) in tomb:
                continue
            csubj, cobj = remap.get(subj, subj), remap.get(obj, obj)
            if csubj == subj and cobj == obj:
                continue
            try:
                store.retract(subj, pred, obj, reason="compaction_alias_merge")
                store.add(csubj, pred, cobj)  # exact de-dup collapses collisions
                rewritten += 1
            except Exception:
                continue
        store.flush()

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "clusters": len(clusters), "nodes_merged": merged_nodes,
                             "rewritten": rewritten, "canonical": canon_ledger[:50]},
                            ensure_ascii=False) + "\n")
    return {"clusters": len(clusters), "rewritten": rewritten,
            "nodes_merged": merged_nodes}
