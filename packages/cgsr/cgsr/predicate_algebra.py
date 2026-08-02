"""Predicate algebra — reasoning VM v2 ( P3, the Datalog insight).

The tension: every new reasoning type used to need a new hand-built reasoner,
brushing against the hard rule "knowledge goes to the GRAPH, never to code".
Resolution: code holds only a FIXED, small operator algebra; WHICH predicates
have WHICH algebraic properties is data (data/lexicon/predicate_properties.json,
plus properties INDUCED from the observed graph itself). A new reasoning type is
a new predicate annotation, not new code.

Operators (all bounded, all emitting derivation traces for XAI):
 - transitive closure (p transitive: aPb, bPc ⊢ aPc)
 - symmetry expansion (p symmetric: aPb ⊢ bPa)
 - inverse mapping (p inverse q: aPb ⊢ bQa)
 - IS_A inheritance (p inheritable: a IS_A b, bPv ⊢ aPv)
 - functional conflict (p functional: aPb, aPc, b≠c → CONFLICT, not inference)
 → conflicts feed truth discovery's exclusion groups instead of exploding.

Property induction from data (measure-first, no rule tables):
 - symmetric: enough observed pairs hold in both directions;
 - functional: subjects overwhelmingly map to exactly one object.
 Transitivity is NOT induced (needs too much data to distinguish from chains);
 it stays declared in the lexicon file.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

Fact = tuple[str, str, str]  # (subject, predicate, object)

_DEFAULT_PROPS_PATH = Path(__file__).resolve().parents[3] / "data" / "lexicon" / "predicate_properties.json"
_MAX_DERIVED = 2000


@dataclass
class PredicateProperties:
    transitive: set[str] = field(default_factory=set)
    symmetric: set[str] = field(default_factory=set)
    functional: set[str] = field(default_factory=set)
    inheritable: set[str] = field(default_factory=set)
    inverse: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "PredicateProperties":
        p = Path(path) if path else _DEFAULT_PROPS_PATH
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            transitive=set(raw.get("transitive", [])),
            symmetric=set(raw.get("symmetric", [])),
            functional=set(raw.get("functional", [])),
            inheritable=set(raw.get("inheritable", [])),
            inverse=dict(raw.get("inverse", {})),
        )

    def merged_with(self, other: "PredicateProperties") -> "PredicateProperties":
        return PredicateProperties(
            transitive=self.transitive | other.transitive,
            symmetric=self.symmetric | other.symmetric,
            functional=self.functional | other.functional,
            inheritable=self.inheritable | other.inheritable,
            inverse={**self.inverse, **other.inverse},
        )


@dataclass
class Derived:
    fact: Fact
    operator: str
    trace: list[Fact]

    def to_dict(self) -> dict[str, Any]:
        return {"fact": list(self.fact), "operator": self.operator,
                "trace": [list(t) for t in self.trace]}


@dataclass
class InferenceResult:
    derived: list[Derived]
    conflicts: list[dict[str, Any]]
    truncated: bool = False

    def facts(self) -> set[Fact]:
        return {d.fact for d in self.derived}


def induce_properties(facts: Iterable[Fact], *, min_support: int = 3,
                      symmetric_ratio: float = 0.6, functional_ratio: float = 0.9) -> PredicateProperties:
    """Read algebraic properties off the observed graph — knowledge stays data."""
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    objects_per_subject: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for s, p, o in facts:
        pairs[p].add((s, o))
        objects_per_subject[p][s].add(o)

    props = PredicateProperties()
    for p, ps in pairs.items():
        if len(ps) >= min_support:
            both = sum(1 for (s, o) in ps if (o, s) in ps)
            if both / len(ps) >= symmetric_ratio:
                props.symmetric.add(p)
    for p, subj_map in objects_per_subject.items():
        if p in props.symmetric:
            continue  # a both-directions relation is a LINK, not an attribute — never 1:1
        if len(subj_map) >= min_support:
            single = sum(1 for objs in subj_map.values() if len(objs) == 1)
            if single / len(subj_map) >= functional_ratio:
                props.functional.add(p)
    return props


def infer(facts: Iterable[Fact], props: PredicateProperties, *,
          max_depth: int = 4, max_derived: int = _MAX_DERIVED) -> InferenceResult:
    base: set[Fact] = set(facts)
    known: set[Fact] = set(base)
    derived: list[Derived] = []
    truncated = False

    def _add(fact: Fact, operator: str, trace: list[Fact]) -> bool:
        nonlocal truncated
        if fact in known:
            return False
        if len(derived) >= max_derived:
            truncated = True
            return False
        known.add(fact)
        derived.append(Derived(fact=fact, operator=operator, trace=trace))
        return True

    # 1) symmetry + inverse: single pass over base (results participate in closure below)
    for s, p, o in list(known):
        if p in props.symmetric:
            _add((o, p, s), "symmetry", [(s, p, o)])
        if p in props.inverse:
            _add((o, props.inverse[p], s), "inverse", [(s, p, o)])

    # 2) transitive closure per transitive predicate (bounded BFS with path traces)
    for p in props.transitive:
        edges: dict[str, set[str]] = defaultdict(set)
        for s, pp, o in known:
            if pp == p:
                edges[s].add(o)
        for start in list(edges.keys()):
            frontier = {(start, o): [(start, p, o)] for o in edges[start]}
            for _ in range(max_depth - 1):
                nxt: dict[tuple[str, str], list[Fact]] = {}
                for (a, b), path in frontier.items():
                    for c in edges.get(b, ()):  # a→b→c
                        if c != a and (a, c) not in nxt:
                            nxt[(a, c)] = path + [(b, p, c)]
                if not nxt:
                    break
                for (a, c), path in nxt.items():
                    _add((a, p, c), "transitive_closure", path)
                frontier = nxt

    # 3) IS_A inheritance for inheritable predicates: a IS_A b & b P v ⊢ a P v
    isa_parents: dict[str, set[str]] = defaultdict(set)
    for s, p, o in known:
        if p == "IS_A":
            isa_parents[s].add(o)
    by_subject: dict[str, list[Fact]] = defaultdict(list)
    for f in list(known):
        by_subject[f[0]].append(f)
    for child, parents in list(isa_parents.items()):
        for parent in parents:
            for (ps, pp, po) in by_subject.get(parent, []):
                if pp in props.inheritable:
                    _add((child, pp, po), "isa_inheritance", [(child, "IS_A", parent), (ps, pp, po)])

    # 4) functional conflict detection — never "infer" past a contradiction, expose it
    conflicts: list[dict[str, Any]] = []
    per_sp: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s, p, o in known:
        if p in props.functional:
            per_sp[(s, p)].add(o)
    for (s, p), objs in per_sp.items():
        if len(objs) > 1:
            conflicts.append({"subject": s, "predicate": p, "objects": sorted(objs),
                              "resolution": "exclusion_group -> truth_discovery"})

    return InferenceResult(derived=derived, conflicts=conflicts, truncated=truncated)
