"""Graph-native IS-A / causal composition — deterministic, offline, no LLM.

The same relation-composition idea as the transitive comparison reasoner, applied to two more
relation types the graph naturally holds:

 IS-A inheritance: " . . ?" → ( ⊂ ⊂ )
 property inheritance: " . . ?" → ( )
 causal chain: " . ?" → 

Each premise is decomposed into a typed edge (X ⊂ Y or X ⇒ Y) and the yes/no question is
answered from the TRANSITIVE CLOSURE of those edges — pure composition, not a per-question
rule. Property questions inherit a predicate up the IS-A chain. Answers only "/" when
the relation is actually derivable; otherwise returns None so the web/graph path handles it
(never guesses an entailment the premises don't support). This is the reasoning shape that
gets RICHER as the relation store (the graph) grows — the density that genuinely composes.
"""
from __future__ import annotations

import re
from typing import Any


_ISA = re.compile(
    r"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)(?:의\s*(?:일종|하나|한\s*종류))?\s*(?:이다|이라고|다|에\s*속한다|입니다)\b"
)
# The causal predicate — surface stems of X⇒Y causation, loaded from the system-owned lexicon
# (data/lexicon) rather than hard-coded here, so the learner can extend it. Native verbs like

try:
    from app.services.ko_lexicon import causal_verb_pattern as _causal_pattern

    _CAUSE_VERB = _causal_pattern()
except Exception:  # pragma: no cover - defensive
    _CAUSE_VERB = r"(?:일으키|일으켜|일으킨|유발|초래|야기|불러|부른|부르|이끌|이끈|이어지|이어진|이어져|낳)"

_CAUSE = re.compile(
    r"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)(?:을|를|(?:으)?로)\s+" + _CAUSE_VERB + r"[가-힣]*"
)

_Q_ISA = re.compile(r"([^\s,.。]+?)(?:은|는|이|가|도)\s+([^\s,.。]+?)(?:이|가)?(?:야|이야|인가|이니|니|맞아|맞나|입니까|인가요)\s*[?？]?\s*$")
_Q_CAUSE = re.compile(r"([^\s,.。]+?)(?:은|는|이|가)\s+([^\s,.。]+?)(?:을|를|(?:으)?로)\s+" + _CAUSE_VERB + r"[가-힣]*\s*[?？]?\s*$")

_Q_PROP = re.compile(r"([^\s,.。]+?)(?:은|는|이|가|도)\s+(.+?)\s*[?？]\s*$")


def _closure(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    reach: dict[str, set[str]] = {}
    for a, b in edges:
        reach.setdefault(a, set()).add(b)
        reach.setdefault(b, set())
    changed = True
    while changed:  # Warshall fixpoint = relation composition
        changed = False
        for x in list(reach):
            for mid in list(reach[x]):
                new = reach.get(mid, set()) - reach[x]
                if new:
                    reach[x] |= new
                    changed = True
    return reach


def _yes(detail: str, kind: str, answer: str = "네, 맞아요.") -> dict[str, Any]:
    return {
        "answer": answer,
        "reasoning_certificate": {
            "derivation_kind": kind,
            "anchor_concept": None,
            "steps": [{"type": "compose", "fact": detail}],
            "evidence_concepts": [],
            "confidence": 0.95,
            "confidence_basis": "relation_composition",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
        "confidence": 0.95,
    }


def solve_entailment(question: str, language: str = "ko") -> dict[str, Any] | None:
    text = (question or "").strip()
    if not text:
        return None
    # Separate PREMISES (declarative sentences) from the QUERY (the '?' sentence). Parsing
    # premises and the question from the same span made the question restate itself as a
    # premise and self-match — so split first.
    sents = [s.strip() for s in re.split(r"(?<=[.。?？])\s+", text) if s.strip()]
    q_sent = next((s for s in reversed(sents) if s.rstrip().endswith(("?", "？"))), sents[-1] if sents else text)
    premises = " ".join(s for s in sents if s is not q_sent) or text

    isa_edges = _ISA.findall(premises)
    cause_edges = _CAUSE.findall(premises)


    if len(cause_edges) >= 2:
        qc = _Q_CAUSE.search(q_sent)
        if qc:
            a, z = qc.group(1), qc.group(2)
            reach = _closure(cause_edges)
            if z in reach.get(a, set()):
                return _yes(f"{a} ⇒ … ⇒ {z} (인과 사슬 합성)", "deterministic_causal_chain")
            if a in reach and z in reach:  # both known but not connected → honest no
                return _yes(f"{a} ⇏ {z} (전제에서 연결되지 않음)", "deterministic_causal_chain", "아니요, 전제만으로는 그렇게 이어지지 않아요.")

    if not isa_edges:
        return None
    isa_reach = _closure(isa_edges)
    nodes = set(isa_reach)


    qi = _Q_ISA.search(q_sent)
    if qi:
        a, b = qi.group(1), qi.group(2)
        if b in isa_reach.get(a, set()):
            return _yes(f"{a} ⊂ … ⊂ {b} (IS-A 사슬 합성)", "deterministic_isa_inheritance")
        if a in nodes and b in nodes:  # both known, not connected → honest no
            return _yes(f"{a} ⊄ {b} (IS-A 사슬에 없음)", "deterministic_isa_inheritance", "아니요, 그렇게 분류되지 않아요.")

    # --- property inheritance: a predicate stated of a STRICT ANCESTOR transfers down ---
    qp = _Q_PROP.search(q_sent)
    if qp:
        subj = qp.group(1).strip()
        pred_core = re.sub(r"\s*[?？]$", "", qp.group(2).strip()).strip()
        ancestors = isa_reach.get(subj, set())  # strict: excludes subj itself
        if subj in nodes and ancestors and len(pred_core) >= 2:
            for owner, prop in _PROPERTY.findall(premises):
                if owner in ancestors and _pred_match(pred_core, prop):
                    return _yes(
                        f"{owner}의 속성 '{prop.strip()}' → {subj} (IS-A 상속)",
                        "deterministic_property_inheritance",
                    )
    return None



_PROPERTY = re.compile(r"([^\s,.。]+?)(?:은|는|이|가)\s+(.+?)(?:[.。]|고\s|며\s|$)")


def _pred_match(query_pred: str, stated_pred: str) -> bool:
    """A stated predicate answers the query predicate if they share the content stem —
 containment either way, robust to conjugation (' ' vs ' ')."""
    q = re.sub(r"\s+", "", query_pred)
    s = re.sub(r"\s+", "", stated_pred)
    if len(q) < 2 or len(s) < 2:
        return False
    core = q[:-1] if len(q) > 2 else q  # drop a trailing conjugation syllable
    return core in s or s[: len(core)] in q
