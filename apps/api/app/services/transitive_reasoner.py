"""Graph-native transitive comparison reasoning — deterministic, offline, no LLM.

The point ATANOR keeps making: reasoning should come from COMPOSING the relations a
sentence states, not from a per-question rule. This module does exactly that for the
comparative/ordering class:

 " . ?" → 
 "A B B C A C ?" → A

Each clause "X Y <ADJ>" is decomposed into a directed edge X ─▷ Y meaning
"X ranks above Y on the <ADJ> scale". The answer is read off the TRANSITIVE CLOSURE of
those edges (a Warshall fixpoint — the relation-composition step) — the maximal node, the
minimal node, or the winner of a pairwise reachability test. It is dimension-agnostic: it
never needs to know whether "" means large or small in the world, only that "… "
places one above another on a scale and " " asks for the top of that same scale. So
there is no adjective/knowledge table; the mechanism is general and any comparative relation
the text (or, later, the graph) supplies composes the same way. Returns None when the text is
not a transitive-comparison question, or when premises are contradictory (a cycle).
"""
from __future__ import annotations

import re
from typing import Any




_COMPARE = re.compile(
    r"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)\s*보다\s+(?:더\s+|훨씬\s+)?"
    r"(?:[가-힣]+(?:이|가)\s+(?:더\s+)?)?([가-힣A-Za-z]+)"
)

_PAIR = re.compile(r"([^\s,.。]+?)(?:와|과|랑|이랑)\s+([^\s,.。]+?)\s*중\b(.*)")

# First-syllable antonym map: reconciles a question that mixes an adjective with its opposite

# hard-coded here — it is loaded from the system-owned lexicon (data/lexicon), which the learner
# can extend. Polarity morphology on one shared scale, not world knowledge.
try:
    from app.services.ko_lexicon import antonyms as _load_antonyms

    _ANTONYMS = _load_antonyms()
except Exception:  # pragma: no cover - defensive
    _ANTONYMS = {"작": "크", "적": "많", "낮": "높", "느": "빠", "짧": "길", "어": "많", "좁": "넓", "얕": "깊", "약": "강"}


def _syllable_key(ch: str) -> tuple[int, int] | str:
    """(, ) of a Hangul syllable, dropping and normalizing the -irregular
 contraction →, so conjugated adjective forms collapse to one scale key:
 ···· → all (, ). Non-Hangul returns the raw char."""
    o = ord(ch) if ch else 0
    if not (0xAC00 <= o <= 0xD7A3):
        return ch
    idx = o - 0xAC00
    cho, jung = idx // 588, (idx % 588) // 28
    if jung == 4:
        jung = 18
    return (cho, jung)


def _canon(adj: str) -> tuple[tuple[int, int] | str, bool]:
    """(scale_key, is_positive_direction) for a comparative adjective surface form."""
    a = (adj or "").strip()
    if not a:
        return "", True
    for neg, pos in _ANTONYMS.items():
        if a.startswith(neg):
            return _syllable_key(pos), False
    return _syllable_key(a[0]), True


def _has_batchim(word: str) -> bool:
    o = ord(word[-1]) if word else 0
    return 0xAC00 <= o <= 0xD7A3 and (o - 0xAC00) % 28 != 0


def solve_transitive(question: str, language: str = "ko") -> dict[str, Any] | None:
    text = (question or "").strip()
    if not text:
        return None
    edges: list[tuple[str, str]] = []  # (higher, lower) on the canonical scale
    scales: set[Any] = set()
    for hi, lo, adj in _COMPARE.findall(text):
        scale, positive = _canon(adj)
        scales.add(scale)
        edges.append((hi, lo) if positive else (lo, hi))
    # Need ≥2 linked comparisons on ONE scale to have something to COMPOSE (a single
    # comparison is left to the pairwise web-attribute reasoner / plain retrieval).
    if len(edges) < 2 or len(scales) != 1:
        return None
    scale = next(iter(scales))
    nodes = {n for e in edges for n in e}

    # Transitive closure: above[x] = every node x outranks, directly or via a chain.
    above: dict[str, set[str]] = {n: set() for n in nodes}
    for hi, lo in edges:
        above[hi].add(lo)
    changed = True
    while changed:  # Warshall fixpoint — the relation-composition step
        changed = False
        for x in nodes:
            for mid in list(above[x]):
                new = above[mid] - above[x]
                if new:
                    above[x] |= new
                    changed = True
    if any(x in above[x] for x in nodes):  # cycle → contradictory premises, don't guess
        return None

    steps = [{"type": "relation_edge", "fact": f"{hi} ▷ {lo}"} for hi, lo in edges]

    def _result(answer: str, detail: str) -> dict[str, Any]:
        return {
            "answer": answer,
            "reasoning_certificate": {
                "derivation_kind": "deterministic_transitive_order",
                "anchor_concept": None,
                "steps": steps + [{"type": "compose", "fact": detail}],
                "evidence_concepts": [],
                "confidence": 0.95,
                "confidence_basis": "relation_composition",
                "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
            },
            "confidence": 0.95,
        }


    pair = _PAIR.search(text)
    if pair:
        a, b, tail = pair.group(1), pair.group(2), pair.group(3)
        qadj = next((w for w in re.findall(r"[가-힣A-Za-z]+", tail) if _canon(w)[0] == scale), None)
        if a in nodes and b in nodes and qadj is not None:
            _, q_pos = _canon(qadj)
            if b in above[a]:
                winner, other = (a, b) if q_pos else (b, a)
            elif a in above[b]:
                winner, other = (b, a) if q_pos else (a, b)
            else:
                return None  # not ordered relative to each other → abstain
            return _result(
                f"{winner}{'이' if _has_batchim(winner) else '가'} 더 {qadj}.",
                f"{a}·{b}를 이행적으로 합성 → {winner}",
            )


    # picks max (same direction) or min (negated / antonym).
    sm = re.search(r"(?:가장|제일)\s+(.+?)[?？.]?\s*$", text)
    if sm:
        negated = bool(re.match(r"(안|덜)\s", sm.group(1)))
        for w in re.findall(r"[가-힣A-Za-z]+", sm.group(1)):
            w_scale, w_pos = _canon(w)
            if w_scale != scale:
                continue
            want_top = w_pos and not negated
            if want_top:
                cand = [n for n in nodes if len(above[n]) == len(nodes) - 1]  # outranks all others
            else:
                cand = [n for n in nodes if not above[n]]  # outranks none
            if len(cand) == 1:
                return _result(
                    f"{cand[0]}입니다.",
                    f"이행 순서의 {'최상위' if want_top else '최하위'} = {cand[0]}",
                )
            break
    return None
