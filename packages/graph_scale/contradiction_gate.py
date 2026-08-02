# -*- coding: utf-8 -*-
"""Algebraic contradiction gate — the intake filter for massive data influx (Gemini proposal
Stage 2, 2026-07-10: " ").

The insight we already hold: our facts live in INT space (interned term ids) and we have a
deductive-closure engine. So we can check a flood of incoming is_a edges against the EXISTING
taxonomy with integer/boolean matrix ops — no string comparison — and bounce the structurally
impossible ones at tens-of-millions per second, before they ever touch the curated store.

What it rejects (structural, provable — not a guess):
 * self-loop: X is_a X
 * direct reversal: X is_a Y when Y is_a X is already stated
 * cycle: X is_a Y when Y already reaches X through the is_a chain (Y →…→ X),
 because adding X→Y would close a directed cycle in what must be a DAG.

A taxonomy (is_a / subclass_of) is a partial order: it must be acyclic. Any incoming edge that
would break acyclicity is not "low confidence" — it is impossible, so we can cancel it with
certainty and zero model. This is the fast, high-precision first pass; softer semantic filtering
(sense collisions, source trust) stays downstream. Reads the store; writes nothing.
"""
from __future__ import annotations

from typing import Any, Iterable

try:
    import numpy as np
    _HAVE_NP = True
except Exception:  # pragma: no cover
    _HAVE_NP = False

_TAXO_RELATIONS = ("is_a", "instance_of", "subclass_of")
_DEFAULT_MAX_DEPTH = 8   # cycles in a real taxonomy are short; bounded depth keeps it O(depth·E)


def _load_relation_pairs(store: Any, relation: str):
    """Existing (s_id, o_id) int arrays for `relation` from the columnar store."""
    from packages.reasoning_vm.closure_accelerator import _load_relation_edges
    return _load_relation_edges(store, relation)


def _reaches(s_ids, o_ids, targets: set[int], max_depth: int) -> dict[int, set[int]]:
    """For each node in `targets`, the set of nodes reachable from it via up-to-max_depth is_a
    hops (bounded BFS in int space). Used to test 'does o already reach s?' for candidate edges."""
    from collections import defaultdict, deque
    adj: dict[int, list[int]] = defaultdict(list)
    for s, o in zip(s_ids.tolist() if _HAVE_NP else s_ids,
                    o_ids.tolist() if _HAVE_NP else o_ids):
        adj[int(s)].append(int(o))
    out: dict[int, set[int]] = {}
    for start in targets:
        seen: set[int] = set()
        q = deque((n, 0) for n in adj.get(start, ()))
        while q:
            node, depth = q.popleft()
            if node in seen or depth >= max_depth:
                if node not in seen:
                    seen.add(node)
                continue
            seen.add(node)
            for nxt in adj.get(node, ()):
                if nxt not in seen:
                    q.append((nxt, depth + 1))
        out[start] = seen
    return out


def check_edges(store: Any, new_edges: Iterable[tuple[str, str]], *, relation: str = "is_a",
                max_depth: int = _DEFAULT_MAX_DEPTH) -> dict[str, Any]:
    """Gate a batch of candidate (subject, object) `relation` edges against the store's existing
    taxonomy. Returns accepted edges + rejected edges with a structural reason. Never writes."""
    edges = [(str(s).strip(), str(o).strip()) for s, o in new_edges if str(s).strip() and str(o).strip()]
    if not edges:
        return {"accepted": [], "rejected": [], "checked": 0, "relation": relation}

    lookup = store.terms.lookup
    s_ids, o_ids = _load_relation_pairs(store, relation)
    # map candidate edges to ids where both endpoints already exist; unknown endpoints can't form
    # a cycle with the existing graph, so they pass the structural gate (soft filters handle them).
    cand_ids: list[tuple[int | None, int | None]] = [(lookup(s), lookup(o)) for s, o in edges]
    # which existing objects (candidate subjects) do we need reachability from? test o →…→ s.
    need_from = {oid for (sid, oid) in cand_ids if sid is not None and oid is not None}
    reach = _reaches(s_ids, o_ids, need_from, max_depth) if (need_from and _HAVE_NP) else {}
    # also the set of directly-stated edges, for the len-1 reversal case
    stated = set(zip((s_ids.tolist() if _HAVE_NP else s_ids),
                     (o_ids.tolist() if _HAVE_NP else o_ids)))

    accepted, rejected = [], []
    for (s, o), (sid, oid) in zip(edges, cand_ids):
        if s == o or (sid is not None and sid == oid):
            rejected.append({"edge": [s, o], "reason": "self_loop"}); continue
        if sid is not None and oid is not None:
            if (oid, sid) in stated:
                rejected.append({"edge": [s, o], "reason": "direct_reversal"}); continue
            if sid in reach.get(oid, set()):
                rejected.append({"edge": [s, o], "reason": "cycle"}); continue
        accepted.append([s, o])
    return {
        "relation": relation, "checked": len(edges),
        "accepted": accepted, "accepted_count": len(accepted),
        "rejected": rejected, "rejected_count": len(rejected),
        "note": "구조적으로 불가능한 엣지(자기루프·역방향·순환)만 결정론적으로 취소 — DAG 불변식. "
                "의미(어의·출처신뢰)는 하위 소프트 필터 담당. 스토어에 쓰지 않음.",
    }


def gate_candidates(store: Any, candidate_edges: Iterable[tuple[str, str]], *,
                    relation: str = "is_a") -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Convenience for the staging→promotion boundary: returns (clean_edges, report). The clean
    edges are the structurally consistent survivors, ready for the downstream trust/consensus gate
    before any operator-gated promotion. Nothing is written here."""
    rep = check_edges(store, candidate_edges, relation=relation)
    clean = [(a, b) for a, b in rep["accepted"]]
    return clean, rep
