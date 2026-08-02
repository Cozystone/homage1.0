"""Curated-KG-as-judge: contradiction detection for learned facts.

The measured top residual hallucination class is a WRONG FACT inside the learned graph
(→" ", is_a ): extraction noise that slipped past the consensus gate
and is then answered faithfully. The engine isn't lying — its source is wrong.

The judge uses the asset we already have: the curated TripleStore (Wikidata-grade,
human-verified). Before a learned (s, p, o) is promoted into an answerable store, ask the
curated store for a verdict:

 consistent curated store holds the same (s, p, o) — promote with raised trust
 contradicted curated store holds (s, p, o') with o' != o for a FUNCTIONAL predicate
 (one that admits a single value: a country has ONE capital) — quarantine
 type_conflict the candidate's is_a parent is declared disjoint (via disjoint_with edges
 IN THE STORE — knowledge stays in the graph, never in code) with a parent
 the store already asserts — quarantine
 unknown curated store has no evidence — the normal consensus gate applies

Honesty: the judge never invents; it only compares against stored curated facts. An
'unknown' verdict is NOT a pass — it just means this gate has nothing to say and the
existing k-source consensus machinery remains the gate.
"""
from __future__ import annotations

from typing import Any

# Predicates where one subject admits exactly one object (functional). This is RELATION
# ALGEBRA (like RELATION_ALGEBRA in inference.py) — a property of the relation NAME, not
# world knowledge, so it is allowed in code.
FUNCTIONAL_PREDICATES = frozenset({"capital", "capital_of", "country", "birth_date", "death_date"})

_MAX_FACTS = 64          # bounded per-subject scan


def judge(subject: str, predicate: str, obj: str, store: Any) -> dict[str, Any]:
    """Verdict for a candidate learned fact against the curated store. Returns
    {verdict, evidence} where evidence is the curated fact(s) that decided it."""
    if store is None or len(store) == 0:
        return {"verdict": "unknown", "evidence": []}
    facts = store.facts_about(subject, limit=_MAX_FACTS)
    if not facts:
        return {"verdict": "unknown", "evidence": []}

    same_pred = [(s, p, o) for (s, p, o) in facts if p == predicate]
    for s, p, o in same_pred:
        if o == obj:
            return {"verdict": "consistent", "evidence": [f"{s} {p} {o}"]}
    if predicate in FUNCTIONAL_PREDICATES and same_pred:
        # curated store asserts a DIFFERENT single value → the candidate is wrong
        return {"verdict": "contradicted",
                "evidence": [f"{s} {p} {o}" for (s, p, o) in same_pred[:3]]}

    if predicate == "is_a":
        # type-conflict: the store's disjoint_with edges (graph content, not code) say the
        # candidate parent cannot coexist with an already-asserted parent.
        asserted_parents = [o for (_, p, o) in facts if p == "is_a"]
        for parent in asserted_parents:
            for _, dp, dis in store.facts_about(parent, limit=_MAX_FACTS):
                if dp == "disjoint_with" and dis == obj:
                    return {"verdict": "type_conflict",
                            "evidence": [f"{subject} is_a {parent}", f"{parent} disjoint_with {obj}"]}
            # symmetric check: disjoint declared on the candidate side
        for _, dp, dis in store.facts_about(obj, limit=_MAX_FACTS):
            if dp == "disjoint_with" and dis in asserted_parents:
                return {"verdict": "type_conflict",
                        "evidence": [f"{subject} is_a {dis}", f"{obj} disjoint_with {dis}"]}

    return {"verdict": "unknown", "evidence": []}


def filter_candidates(candidates: list[tuple[str, str, str]], store: Any) -> dict[str, Any]:
    """Split candidate facts into promotable / quarantined by curated verdict. Quarantined
    entries keep the evidence so a human (or the review queue) can see WHY."""
    promotable: list[tuple[str, str, str]] = []
    quarantined: list[dict[str, Any]] = []
    for s, p, o in candidates:
        v = judge(s, p, o, store)
        if v["verdict"] in ("contradicted", "type_conflict"):
            quarantined.append({"fact": (s, p, o), **v})
        else:
            promotable.append((s, p, o))
    return {"promotable": promotable, "quarantined": quarantined}
