# -*- coding: utf-8 -*-
"""Sense partitioning — the root-disease fix, started where it's structural.

THE measured disease of this graph (it bit every subsystem today): knowledge is
keyed by SURFACE STRING. One node '' mixes water//suffix senses; 'capital'
mixes column-top/money/city; 'jigsaw' carries 1,315 unrelated is_a parents.
Every lane (bridge, derivation, phase space, soft resolve, the mini) had to grow
its own guard against the same thing.

This module partitions a polysemous term's EDGES into senses — the structural
cut the guards were approximating. The boundary follows the house rule:

 * PROPOSE (soft): the 64D phase space clusters the term's is_a parents —
 parents that resonate belong to one reading;
 * VERIFY (hard): two parents may share a cluster only with SYMBOLIC support —
 a shared stated grandparent type, or membership in the same induced
 definition-sense signature (sense_split). No symbolic support, no merge;
 * the output is a derived, versioned view (like the phase space) — the
 append-only store is never rewritten. Consumers resolve through it.

Downstream (successors wire these): per-sense transitive closure (the 0.45%
guard-skipped hubs become derivable cleanly), sense-scoped answers, sense-aware
soft-resolve. partition_report() is the human/battery-facing view.

STATUS + MEASURED FINDING (2026-07-09, Fable5 handoff — read before wiring):
this is a correct SKELETON whose clustering is NOT yet acceptance-grade, and
the reason is load-bearing. On 'capital' (109 parents) a 54-parent junk
cluster survives every gate tightening (generic-grandparent filter, gp-only
merge license), because those parents — 'assertion', 'citizen', 'change of
magnitude' — are not senses of capital at all: they are INDIVIDUALLY FALSE
edges (base parse noise). The hub disease has two layers:
 (1) true polysemy (capital = // — a handful of real senses),
 (2) parse garbage (capital is_a assertion — belongs to NO sense).
Partitioning addresses (1) and cannot rescue (2). The required pipeline is
TRUST-FILTER FIRST (evidence counting / provenance — the consensus machinery
exists), THEN partition the survivors, THEN per-sense closure. Do not wire
this into any answer or derivation lane until that order is honored."""
from __future__ import annotations

from typing import Any

from .sense_split import content_words, induce_senses


def _resonance(a: str, b: str) -> float | None:
    try:
        from .phase_space import resonance

        return resonance(a, b)
    except Exception:
        return None


def _parents(store: Any, term: str, limit: int = 400) -> list[str]:
    # STAGE 1 -> STAGE 2 pipeline: partition runs on TRUST-FILTERED parents, so
    # the WordNet attractor batch (capital is_a Animal/class/…) is gone before
    # clustering ever sees it. Falls back to raw parents if the filter errors.
    try:
        from .sense_trust_filter import trusted_parents

        tp = trusted_parents(store, term)
        if tp:
            return tp[:limit]
    except Exception:
        pass
    out: list[str] = []
    try:
        for s, p, o in store.facts_about(term, limit=limit) or []:
            if p in ("is_a", "instance_of", "subclass_of") and o and o != term:
                if o not in out:
                    out.append(str(o))
    except Exception:
        pass
    return out


def _grandparents(store: Any, term: str, limit: int = 24) -> set[str]:
    out: set[str] = set()
    try:
        for s, p, o in store.facts_about(term, limit=limit) or []:
            if p in ("is_a", "instance_of", "subclass_of"):
                out.add(str(o))
    except Exception:
        pass
    return out


def partition_parents(store: Any, term: str, *, max_parents: int = 400,
                      near: float = 0.6) -> list[dict[str, Any]]:
    """Partition `term`'s is_a parents into sense clusters.

 Greedy agglomerative over parents. A parent joins a cluster only when BOTH
 hold against any member:
 soft: phase resonance >= `near` (or unknown — then symbolic must carry)
 hard: shared stated grandparent type, OR both parents' words hit the
 same induced definition-sense signature.
 Clusters are anchored to induced senses where signatures match, so the
 water-cluster of carries #0's gloss. Returns clusters best-first:
 [{sense_id, gloss, parents, grandparent_types, size}]."""
    parents = _parents(store, term, limit=max_parents)
    if len(parents) < 2:
        return []
    senses = induce_senses(term)
    sense_sig = [(s.sense_id, s.gloss, s.signature) for s in senses]
    gp: dict[str, set[str]] = {p: _grandparents(store, p) for p in parents}
    # DISCRIMINATIVE grandparents only (measured: WordNet upper-ontology labels
    # — entity/abstraction/… — are grandparents of nearly everything, so the
    # symbolic gate passed every merge and one 54-parent junk cluster formed).
    # A grandparent shared by more than a quarter of THIS term's parents carries
    # no sense signal here; drop it from the gate.
    from collections import Counter
    gp_freq: Counter = Counter()
    for s_ in gp.values():
        gp_freq.update(s_)
    cutoff = max(2, len(parents) // 4)
    generic = {g for g, c in gp_freq.items() if c > cutoff}
    gp = {p: (s_ - generic) for p, s_ in gp.items()}

    def _sense_hit(label: str) -> str | None:
        words = set(content_words(label))
        # a parent label's words hitting a sense signature anchors it there
        for sid, _g, sig in sense_sig:
            if words & sig:
                return sid
        return None

    clusters: list[dict[str, Any]] = []
    for p in parents:
        p_gp = gp[p]
        p_sense = _sense_hit(p)
        home = None
        for c in clusters:
            # HARD gate: ONLY a shared discriminative grandparent licenses a
            # merge. (An induced-sense signature hit was tried as an alternate
            # license and measured too permissive — single-word English labels
            # matched broad signatures and one 54-parent junk cluster formed.
            # sense hits now only LABEL clusters, never merge them.)
            if not (p_gp & c["gp"]):
                continue
            # SOFT gate: if phases exist for the pair, they must agree
            ok = True
            for q in c["parents"][:4]:
                w = _resonance(p, q)
                if w is not None and w < near:
                    ok = False
                    break
            if ok:
                home = c
                break
        if home is None:
            clusters.append({"parents": [p], "gp": set(p_gp), "sense_hint": p_sense})
        else:
            home["parents"].append(p)
            home["gp"].update(p_gp)
            if home["sense_hint"] is None:
                home["sense_hint"] = p_sense

    gloss_by_sid = {sid: g for sid, g, _ in sense_sig}
    out = []
    for i, c in enumerate(sorted(clusters, key=lambda c: -len(c["parents"]))):
        sid = c["sense_hint"] or f"{term}#p{i}"
        out.append({
            "sense_id": sid,
            "gloss": gloss_by_sid.get(sid, "")[:80],
            "parents": c["parents"],
            "grandparent_types": sorted(c["gp"])[:6],
            "size": len(c["parents"]),
        })
    return out


def partition_report(store: Any, term: str) -> dict[str, Any]:
    """Human/battery view: is this term's edge set one reading or several?"""
    clusters = partition_parents(store, term)
    return {
        "term": term,
        "parents": sum(c["size"] for c in clusters),
        "clusters": len(clusters),
        "polysemous_edges": len(clusters) > 1,
        "partition": [{"sense_id": c["sense_id"], "gloss": c["gloss"],
                       "size": c["size"], "sample": c["parents"][:6]}
                      for c in clusters[:8]],
    }


# ---- STAGE 3: per-sense closure (the payoff of stages 1+2) ------------------
def per_sense_closure_candidates(store: Any, term: str,
                                 max_per_sense: int = 40) -> list[dict[str, Any]]:
    """Sense-scoped 2-hop closure for ONE hub: within each sense cluster, the
    trusted grandparents of the cluster's parents are sound is_a candidates for
    `term` IN THAT SENSE — the closure that blind derivation got ~30% wrong is
    now scoped to a single reading. PROPOSE-only (candidates carry their sense
    and provenance; the evidence gates decide promotion, as everywhere)."""
    from .sense_trust_filter import trusted_parents

    out: list[dict[str, Any]] = []
    existing = {o for _s, p, o in (store.facts_about(term, limit=400) or [])
                if p == "is_a"}
    for cluster in partition_parents(store, term):
        if cluster["size"] < 2:
            continue                       # a singleton sense has no 2-hop support
        seen: set[str] = set()
        for parent in cluster["parents"]:
            for gp in trusted_parents(store, parent):
                if gp and gp != term and gp not in existing and gp not in seen:
                    seen.add(gp)
                    out.append({"candidate": (term, "is_a", gp),
                                "sense_id": cluster["sense_id"],
                                "via": parent,
                                "support": cluster["size"]})
                    if len(seen) >= max_per_sense:
                        break
            if len(seen) >= max_per_sense:
                break
    return out
