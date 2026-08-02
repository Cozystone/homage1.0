# -*- coding: utf-8 -*-
"""Deductive closure with proof certificates — new truths, each with its proof.

The second half of the reasoning VM: conclude facts that are NOT stored, by
RULE over facts that are, and emit a PROOF for every conclusion. This is the
"synthetic-algebraic reasoning" layer's cornerstone — deterministic forward
chaining, hallucination-safe by the same one-line invariant as the recursive
realizer: the output is a subset of the deductive closure of (stated facts ∪
inference rules), so nothing is concluded that the rules cannot prove.

Rules are DECLARATIVE and minimal (the algebra of relations already used
elsewhere — transitivity, type inheritance, symmetry, relation composition);
each firing records its premises so a conclusion carries a full proof tree.
A conclusion already stated is not re-derived; a conclusion is emitted at most
once, by its shortest proof (BFS over rule firings)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

Fact = tuple[str, str, str]

# minimal, auditable rule set (extend by adding to these — never hard-code facts)
TRANSITIVE = {"is_a", "part_of", "located_in", "subclass_of", "ancestor_of",
              "before", "greater_than"}
SYMMETRIC = {"sibling_of", "spouse_of", "adjacent_to", "alias"}
# relation composition: p ∘ q ⇒ r   (a p b) ∧ (b q c) ⇒ (a r c)
COMPOSE: dict[tuple[str, str], str] = {
    ("capital_of", "located_in"): "located_in",   # capital_of ∘ located_in
    ("is_a", "located_in"): "located_in",
    ("part_of", "part_of"): "part_of",
}
# type inheritance: (x is_a T) ∧ (T has_property P) ⇒ (x has_property P)
INHERIT_PREDICATES = {"is_a", "instance_of"}


@dataclass
class Proof:
    conclusion: Fact
    rule: str
    premises: list[Fact]
    depth: int

    def to_dict(self) -> dict[str, Any]:
        return {"conclusion": list(self.conclusion), "rule": self.rule,
                "premises": [list(p) for p in self.premises], "depth": self.depth}


@dataclass
class DeductionResult:
    derived: dict[Fact, Proof] = field(default_factory=dict)

    def facts(self) -> set[Fact]:
        return set(self.derived)

    def proof_of(self, fact: Fact) -> Proof | None:
        return self.derived.get(fact)

    def certificate(self, fact: Fact) -> dict[str, Any] | None:
        """A full proof TREE for one derived fact: unfold each premise that was
        itself derived, so the certificate bottoms out in stated facts."""
        p = self.derived.get(fact)
        if not p:
            return None
        return {
            "conclusion": list(fact), "rule": p.rule,
            "basis": "output ⊆ deductive closure(stated facts ∪ rules)",
            "steps": [self.certificate(pr) or {"stated_fact": list(pr)}
                      for pr in p.premises],
        }


def deduce(stated: Iterable[Fact], *, max_depth: int = 4,
           max_facts: int = 5000,
           inherit_props: dict[str, list[Fact]] | None = None) -> DeductionResult:
    """Forward-chain the rules over `stated` to a bounded deductive closure.
    Returns only DERIVED facts (not the stated ones), each with its shortest
    proof. `inherit_props` maps a type -> its property facts, enabling the
    type-inheritance rule without scanning the whole store."""
    stated_set: set[Fact] = set(stated)
    res = DeductionResult()

    # adjacency for composition/transitivity
    out: dict[str, list[Fact]] = {}
    for f in stated_set:
        out.setdefault(f[0], []).append(f)

    def known(f: Fact) -> bool:
        return f in stated_set or f in res.derived

    def emit(f: Fact, rule: str, premises: list[Fact], depth: int) -> bool:
        if f[0] == f[2] or known(f):         # no self-loops, no re-derivation
            return False
        res.derived[f] = Proof(f, rule, premises, depth)
        out.setdefault(f[0], []).append(f)
        return True

    # BFS so each fact gets its SHORTEST proof
    frontier: deque[tuple[Fact, int]] = deque((f, 0) for f in stated_set)
    while frontier and len(res.derived) < max_facts:
        (s, p, o), d = frontier.popleft()
        if d >= max_depth:
            continue
        # transitivity: (s p o) ∧ (o p o2) ⇒ (s p o2)
        if p in TRANSITIVE:
            for (s2, p2, o2) in out.get(o, []):
                if p2 == p:
                    nf = (s, p, o2)
                    if emit(nf, f"transitivity[{p}]", [(s, p, o), (s2, p2, o2)], d + 1):
                        frontier.append((nf, d + 1))
        # symmetry: (s p o) ⇒ (o p s)
        if p in SYMMETRIC:
            nf = (o, p, s)
            if emit(nf, f"symmetry[{p}]", [(s, p, o)], d + 1):
                frontier.append((nf, d + 1))
        # composition: (s p o) ∧ (o q c) ⇒ (s r c)
        for (s2, q, c) in out.get(o, []):
            r = COMPOSE.get((p, q))
            if r:
                nf = (s, r, c)
                if emit(nf, f"compose[{p}∘{q}⇒{r}]", [(s, p, o), (s2, q, c)], d + 1):
                    frontier.append((nf, d + 1))
        # type inheritance: (s is_a T) ∧ (T has P) ⇒ (s has P)
        if p in INHERIT_PREDICATES and inherit_props:
            for (t, hp, hv) in inherit_props.get(o, []):
                nf = (s, hp, hv)
                if emit(nf, f"inherit[{o}]", [(s, p, o), (t, hp, hv)], d + 1):
                    frontier.append((nf, d + 1))
    return res


def answer_yes_no(stated: Iterable[Fact], query: Fact, *,
                  max_depth: int = 4) -> dict[str, Any] | None:
    """Decide a closed (s,p,o) query by deduction, returning the verdict WITH a
    proof, or None if neither the fact nor its derivation is found (honest 'I
    can't prove it' — never a guessed yes/no)."""
    stated_set = set(stated)
    if query in stated_set:
        return {"answer": True, "basis": "stated", "proof": {"stated_fact": list(query)}}
    res = deduce(stated_set, max_depth=max_depth)
    if query in res.derived:
        return {"answer": True, "basis": "derived", "proof": res.certificate(query)}
    return None
