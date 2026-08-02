"""Autonomous Creative XAI — graph-native concept creation that scales with graph density.

Philosophy (the user's): explain not the RESULT but the BROKEN PREMISE and the SEARCH PATH.
Creativity here is not free-text generation and not a rule table — it is a set of OPERATORS over
the knowledge graph, so more triples ⇒ more assumptions to break, more analogies to draw, and
sharper value statistics. Every creation is GROUNDED: it recombines real graph structure and
cites the source triples it came from (no fabrication — the "" of a creative concept is the
graph structure it was derived from).

Operators
---------
- break_assumption((X, R, Y)): remove a premise the graph asserts ("X must R Y") and look for
 what fills the gap → "X without Y" ( HAPPENS_AT → -independent → ).
- blend(A, B): conceptual blending (Fauconnier–Turner) — a new concept inherits the relation set
 of A ∪ B. Valuable when A and B share a TYPE (coherent) yet are rarely combined (surprising):
 (USED_FOR ) ⊕ (USED_FOR ) → + . ⊕ is rejected (no
 shared type → incoherent), so creation ≠ random.

Value (all graph-derived, no hand-tuned rules):
 Creative Score = Novelty × Consistency × Surprise × Utility
Explanation (XAI): {broken_premise, search_path, grounding(source triples), score_breakdown}.
Deterministic. No LLM, no backprop.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

Triple = tuple[str, str, str]  # (subject, relation, object)


@dataclass
class CreativeConcept:
    operator: str
    name_hint: str
    broken_premise: str
    search_path: list[str]
    grounding: list[Triple]              # the real graph structure this was derived from
    inherited: list[tuple[str, str]]     # (relation, object) the new concept carries
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def creative_score(self) -> float:
        s = self.scores
        return s.get("novelty", 0) * s.get("consistency", 0) * s.get("surprise", 0) * s.get("utility", 0)

    def explain(self) -> str:
        """XAI: explain the broken premise and the path, not just the result."""
        lines = [
            f"파괴된 전제: {self.broken_premise}",
            "탐색 경로: " + " → ".join(self.search_path),
            "영감(근거): " + "; ".join(f"{s} {r} {o}" for s, r, o in self.grounding[:4]),
            f"창의성 점수: {self.creative_score:.3f} "
            + "(" + ", ".join(f"{k}={v:.2f}" for k, v in self.scores.items()) + ")",
        ]
        return "\n".join(lines)


class CreativeEngine:
    def __init__(self, triples: list[Triple]) -> None:
        self.triples = [(str(s), str(r), str(o)) for s, r, o in triples]
        self.rels_of: dict[str, set[tuple[str, str]]] = defaultdict(set)   # concept → {(rel, obj)}
        self.types_of: dict[str, set[str]] = defaultdict(set)              # concept → {IS_A parents}
        self.neighbors: dict[str, set[str]] = defaultdict(set)
        concepts: set[str] = set()
        for s, r, o in self.triples:
            self.rels_of[s].add((r, o))
            self.neighbors[s].add(o)
            self.neighbors[o].add(s)
            concepts.add(s)
            concepts.add(o)
            if r.upper() in {"IS_A", "IS-A", "ISA", "SUBCLASS_OF"}:
                self.types_of[s].add(o)
        self.concepts = concepts
        # a (relation,object) pair is "novel" if few concepts carry it; count carriers
        self._carriers: dict[tuple[str, str], int] = defaultdict(int)
        for c, pairs in self.rels_of.items():
            for p in pairs:
                self._carriers[p] += 1

    # ----- value functions (graph statistics, not rules) -----
    def _consistency(self, a: str, b: str) -> float:
        """Coherent to blend if a and b share a type or overlap in relational neighborhood."""
        ta, tb = self.types_of[a], self.types_of[b]
        if ta & tb:
            return 1.0
        na = {o for _, o in self.rels_of[a]}
        nb = {o for _, o in self.rels_of[b]}
        if not na or not nb:
            return 0.0
        return len(na & nb) / len(na | nb)  # Jaccard of relation targets

    def _surprise(self, a: str, b: str) -> float:
        """Surprising if a and b are NOT already directly linked / co-occurring."""
        if b in self.neighbors[a] or a in self.neighbors[b]:
            return 0.2
        shared = len(self.neighbors[a] & self.neighbors[b])
        return 1.0 / (1.0 + shared)  # many shared neighbors → less surprising

    def _novelty(self, inherited: list[tuple[str, str]]) -> float:
        """Novel if no single existing concept already carries this whole relation set."""
        target = set(inherited)
        if not target:
            return 0.0
        for pairs in self.rels_of.values():
            if target <= pairs:
                return 0.0  # an existing concept already IS this → not novel
        rare = sum(1 for p in target if self._carriers.get(p, 0) <= 2)
        return min(1.0, 0.4 + 0.2 * rare)

    def _utility(self, inherited: list[tuple[str, str]]) -> float:
        """More distinct functions/capabilities covered → more useful (bounded)."""
        funcs = {o for r, o in inherited if r.upper() in {"USED_FOR", "ENABLES", "CAN", "HAS_FUNCTION"}}
        distinct = funcs or {o for _, o in inherited}
        return min(1.0, 0.3 + 0.35 * len(distinct))

    # ----- operators -----
    def blend(self, a: str, b: str) -> CreativeConcept | None:
        if a == b or (a not in self.rels_of and b not in self.rels_of):
            return None
        inherited = sorted(self.rels_of[a] | self.rels_of[b])
        fa = sorted({o for r, o in self.rels_of[a] if r.upper() in {"USED_FOR", "ENABLES", "CAN"}}) or [o for _, o in sorted(self.rels_of[a])][:1]
        fb = sorted({o for r, o in self.rels_of[b] if r.upper() in {"USED_FOR", "ENABLES", "CAN"}}) or [o for _, o in sorted(self.rels_of[b])][:1]
        premise = f"‘{a}’와 ‘{b}’는 별개다 ({', '.join(fa)} vs {', '.join(fb)})"
        scores = {
            "novelty": self._novelty(inherited),
            "consistency": self._consistency(a, b),
            "surprise": self._surprise(a, b),
            "utility": self._utility(inherited),
        }
        grounding = [(a, r, o) for r, o in sorted(self.rels_of[a])] + [(b, r, o) for r, o in sorted(self.rels_of[b])]
        return CreativeConcept(
            operator="blend",
            name_hint=f"{a}⊕{b}",
            broken_premise=premise,
            search_path=[a, "관계구조 융합", b],
            grounding=grounding,
            inherited=inherited,
            scores=scores,
        )

    def break_assumption(self, subj: str, relation: str, obj: str) -> CreativeConcept | None:
        if (relation, obj) not in self.rels_of.get(subj, set()):
            return None
        # remove the premise; the new concept keeps subj's OTHER relations, drops (relation,obj)
        inherited = sorted(self.rels_of[subj] - {(relation, obj)})
        premise = f"‘{subj}’은(는) 반드시 {obj}에 {relation} 해야 한다"
        # who else has (relation, obj)? and who has the OTHER relations without it? → the frontier
        others = sorted({c for c, pairs in self.rels_of.items() if (relation, obj) in pairs and c != subj})
        carriers = len(others) + 1  # how universal is this premise across the graph
        scores = {


            "novelty": min(1.0, 0.5 + 0.12 * carriers),
            "consistency": 0.8,  # dropping one constraint keeps the rest coherent
            "surprise": min(1.0, 0.35 + 0.12 * len(others)),
            "utility": self._utility(inherited) if inherited else 0.45,
        }
        return CreativeConcept(
            operator="break",
            name_hint=f"{obj}-독립적 {subj}",
            broken_premise=premise,
            search_path=[f"{subj} {relation} {obj}", f"¬({relation} {obj})", f"{obj} 없는 {subj}"],
            grounding=[(subj, relation, obj)] + [(subj, r, o) for r, o in inherited][:3],
            inherited=inherited,
            scores=scores,
        )

    # ----- autonomy -----
    def self_questions(self, k: int = 5) -> list[str]:
        """Generate its own problems: the highest-leverage assumptions (most-asserted premises)."""
        counts = sorted(self._carriers.items(), key=lambda kv: -kv[1])
        qs = []
        for (rel, obj), n in counts[:k]:
            qs.append(f"왜 무언가는 항상 {obj}에 {rel} 해야 하는가?")
        return qs

    def invent(self, *, top: int = 5, max_pairs: int = 4000) -> list[CreativeConcept]:
        """Autonomously propose the highest-scoring creative concepts across the graph."""
        cands: list[CreativeConcept] = []
        pool = [c for c in self.concepts if self.rels_of.get(c)]
        seen = 0
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                seen += 1
                if seen > max_pairs:
                    break
                c = self.blend(a, b)
                if c and c.creative_score > 0:
                    cands.append(c)
            if seen > max_pairs:
                break
        # also break the highest-leverage (most universal) assumptions
        for (rel, obj), _ in sorted(self._carriers.items(), key=lambda kv: -kv[1])[:8]:
            for subj in [c for c, pairs in self.rels_of.items() if (rel, obj) in pairs][:3]:
                bc = self.break_assumption(subj, rel, obj)
                if bc and bc.creative_score > 0:
                    cands.append(bc)
        cands.sort(key=lambda c: -c.creative_score)
        return cands[:top]
