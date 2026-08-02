# -*- coding: utf-8 -*-
"""F3 — relation-path induction: procedures induced over the WORLD GRAPH from examples.

The arithmetic flywheel induced number procedures; F3 induces GRAPH procedures — a relation path
that maps a start entity to an answer entity. Given worked (start, answer) examples — exactly what
the roamer/world-pack sees in text ('France's capital is Paris' → (, )) — it DISCOVERS
which relation, or which composition of relations, connects them, verified on held-out pairs.

This replaces chain_reasoner's hand-written COMPOSE table with induction: the composition
'capital ∘ population' ('X ') is LEARNED from examples, never coded. Same doctrine:
candidate paths come from the relations actually present on the example nodes (grounded, no
explosion); a path is kept only if it reproduces every training example AND every held-out one;
Occam prefers the shortest path. No-LLM, verification-gated — a wrong path is unspeakable.

The world pack (Wikidata) makes this bloom: every functional relation it carries becomes an
inducible procedure the moment a few examples are seen.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable

FactsAbout = Callable[[str], list[tuple[str, str, str]]]
Example = tuple[str, str]                              # (start_entity, answer_entity)
_STRUCTURAL = {"defined_as", "alias", "sense", "qlabel"}   # not relation-path steps


def run_path(start: str, path: tuple[str, ...], facts_about: FactsAbout,
             *, limit: int = 64, max_frontier: int = 200) -> set[str]:
    """Traverse the graph from `start` following each relation in `path`; return reachable
    answers (a set — functional relations yield one)."""
    frontier = {start}
    for rel in path:
        nxt: set[str] = set()
        for node in list(frontier)[:max_frontier]:
            try:
                for _s, p, o in (facts_about(node) or [])[:limit]:
                    if p == rel and o and o != node:
                        nxt.add(o)
            except Exception:
                continue
        frontier = nxt
        if not frontier:
            return set()
    return frontier


@dataclass
class InducedPath:
    name: str
    path: tuple[str, ...]
    fn: Callable[[str], str | None]
    n_train: int
    n_verified: int

    def certificate(self) -> dict[str, Any]:
        return {"induced_procedure": self.name, "relation_path": list(self.path),
                "fit_examples": self.n_train, "verified_held_out": self.n_verified,
                "basis": "relation path discovered from example nodes over the world graph; kept "
                         "only after reproducing every training AND held-out (start→answer) pair — "
                         "an induced composition, never a hand-written rule"}


def _candidate_paths(starts: list[str], facts_about: FactsAbout, max_hops: int,
                     rel_cap: int) -> list[tuple[str, ...]]:
    """Paths grounded in the data: 1-hop = relations present on the start nodes; 2-hop = those
    followed by relations present on their targets. Ordered shortest-first (Occam)."""
    rels1: list[str] = []
    seen1: set[str] = set()
    mids: set[str] = set()
    for s in starts:
        for _s, p, o in (facts_about(s) or []):
            if p in _STRUCTURAL:
                continue
            if p not in seen1:
                seen1.add(p)
                rels1.append(p)
            mids.add(o)
        if len(rels1) >= rel_cap:
            break
    paths: list[tuple[str, ...]] = [(r,) for r in rels1]
    if max_hops >= 2:
        rels2: list[str] = []
        seen2: set[str] = set()
        for m in list(mids)[:rel_cap]:
            for _s, p, _o in (facts_about(m) or []):
                if p in _STRUCTURAL or p in seen2:
                    continue
                seen2.add(p)
                rels2.append(p)
        for r1, r2 in itertools.product(rels1, rels2):
            paths.append((r1, r2))
    return paths


def induce_relation_path(name: str, examples: list[Example], facts_about: FactsAbout,
                         *, max_hops: int = 2, holdout_frac: float = 0.4,
                         rel_cap: int = 40) -> InducedPath | None:
    """Induce the relation path mapping start→answer from examples, verify-gated + Occam."""
    ex = list(examples)
    if len(ex) < 4:
        return None
    k = max(2, int(len(ex) * (1 - holdout_frac)))
    train, held = ex[:k], ex[k:]
    for path in _candidate_paths([s for s, _ in train], facts_about, max_hops, rel_cap):
        if all(ans in run_path(st, path, facts_about) for st, ans in train) \
                and held and all(ans in run_path(st, path, facts_about) for st, ans in held):
            def _fn(start: str, _p=path) -> str | None:
                got = run_path(start, _p, facts_about)
                return next(iter(got)) if len(got) == 1 else (sorted(got)[0] if got else None)
            return InducedPath(name, path, _fn, len(train), len(held))
    return None


def resolving_facts_about(raw: FactsAbout, *, cache: dict[str, str] | None = None) -> FactsAbout:
    """Adapt a raw facts_about for the WORLD-PACK schema, where relation OBJECTS are Wikidata
 Q-ids ( -capital-> Q90) resolved to a label via their own 'qlabel' row (Q90 -qlabel-> ).
 Wrapping the store's facts_about with this makes run_path()/induce_relation_path() traverse AND
 return READABLE entities — so F3 grounds cleanly against the world pack. No-op on label-object
 stores (kg_triples): nothing matches ^Q\\d+$, so every row passes through untouched."""
    import re
    _qid = re.compile(r"^Q\d+$")
    cache = {} if cache is None else cache

    def _label(qid: str) -> str:
        if qid in cache:
            return cache[qid]
        lab = qid
        try:
            for _s, p, o in (raw(qid) or []):
                if p == "qlabel" and o:
                    lab = str(o)
                    break
        except Exception:
            pass
        cache[qid] = lab
        return lab

    def facts(node: str) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        for s, p, o in (raw(node) or []):
            os = str(o)
            if p != "qlabel" and _qid.match(os):
                os = _label(os)
            out.append((str(s), str(p), os))
        return out

    return facts
