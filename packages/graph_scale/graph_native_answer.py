# -*- coding: utf-8 -*-
"""Graph-native answer composer — the brain-like pipeline's mouth.

conceptualize (anchor + focus relation) -> spreading_activation (lit subgraph = context)
-> THIS: select the cleanest, brightest facts from the field and compose grounded prose.

Why this exists: the old path answered " ?" with a single-edge template ("
") — a lookup, not understanding. Here the activation field has already lit , its
kind, its container, and 's own definition/; we compose a DEEP answer that follows the
graph outward ("… . ."), context carried across hops.

Hallucination-safe: every clause verbalizes a stored, activation-ranked fact. Noise the store
still carries (English placeholder labels, garbage is_a chains) is filtered at VERBALIZATION —
we only ever SPEAK clean Korean concept facts, never invent. Relation weights / thresholds are
Phase-B-evolvable; this composer is the fixed, auditable surface over the evolving field.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .spreading_activation import spread, ActivatedSubgraph

_HANGUL = re.compile(r"[가-힣]")
# placeholder labels that must never be SPOKEN as a concept (pure graph plumbing)
_JUNK_LABEL = re.compile(r"^(Q\d+|entity|thing|unknown|무엇|무언가|것|종류|개념|대상)$", re.I)
# common Wikidata/ontology CLASS labels (English) -> Korean, so an English is_a target becomes

_CLASS_KO = {
    "disease": "질병", "settlement": "도시", "city": "도시", "town": "도시", "human settlement": "도시",
    "country": "나라", "sovereign state": "나라", "human": "사람", "person": "사람",
    "scientist": "과학자", "chemical element": "화학 원소", "chemical compound": "화합물",
    "company": "기업", "language": "언어", "animal": "동물", "plant": "식물", "food": "음식",
    "occupation": "직업", "profession": "직업", "organization": "조직", "river": "강",
    "mountain": "산", "planet": "행성", "star": "별", "emotion": "감정", "color": "색",
}
# relation -> Korean predicate surface (spoken tail clause). Relation-TYPE, not per-entity.
_REL_KO = {
    "capital": "수도는", "수도": "수도는",
    "located_in": "위치는", "country": "속한 나라는", "part_of": "일부로 속한 곳은",
    "causes": "결과로", "결과": "결과로", "used_for": "쓰임은",
    "created_by": "만든 이는", "발견자": "발견한 이는", "발견": "발견한 이는",
    "원인": "원인은", "인구": "인구는", "면적": "면적은",
}


def _clean_concept(label: str) -> bool:
    """True only for a Korean concept label worth speaking (not English/placeholder/gloss)."""
    label = (label or "").strip()
    return bool(label and len(label) <= 24 and _HANGUL.search(label)
                and not _JUNK_LABEL.match(label) and label.count(" ") <= 1)


def _concept_ko(label: str) -> str | None:
    """The speakable Korean form of a concept label: the label itself if it is clean Korean, else
 the Korean of a known ontology CLASS ('Disease'→''), else None (unspeakable — never invent)."""
    label = (label or "").strip()
    if _clean_concept(label):
        return label
    return _CLASS_KO.get(label.lower())


# dictionary junk that must never be spoken as a description: grammar notes, romanization

_GRAMMAR_NOTE = re.compile(r"(붙어|뒤에\s*쓰여|어미|접사|준말|어근|어간|옛말|방언|romanization|"
                           r"determiner of|\(.*\)|활\s*등급|책장을)")


def _clean_def(o: str) -> str | None:
    """A definition worth SPEAKING: a Korean descriptive phrase, not a grammar note / romanization
    / bare-name gloss. Returns the trimmed lead clause, or None."""
    o = (o or "").strip()
    if not o or not _HANGUL.search(o) or _GRAMMAR_NOTE.search(o):
        return None
    lead = o.split(".")[0].strip()

    lead = re.sub(r"\s*(이름|명칭)$", "", lead).strip()
    return lead or None


def _dominant_def(anchor: str, props: list[tuple[str, str, str]]) -> str | None:
    """The anchor's dominant-sense Korean definition (frequency = dominance; the same signal
    used in answer_bridge — a polysemy hub's better-supported sense wins over a rare homonym)."""
    ko = [o for (_s, p, o) in props if p == "defined_as" and _clean_def(o)]
    if not ko:
        return None

    def support(o: str) -> int:
        return sum(1 for o2 in ko if o == o2 or (len(o) >= 6 and len(o2) >= 6 and o[:6] == o2[:6])
                   or o in o2 or o2 in o)
    ko.sort(key=lambda o: (support(o), len(o)), reverse=True)
    return _clean_def(ko[0])


def _batchim(word: str) -> bool:
    c = ord(word[-1]) if word else 0
    return 0xAC00 <= c <= 0xD7A3 and bool((c - 0xAC00) % 28)


def _topic(word: str) -> str:
    if not word:
        return word
    c = ord(word[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return word + ("은" if (c - 0xAC00) % 28 else "는")
    return word + "는"


def _tail_clause(pred: str, obj: str) -> str | None:
    """Object-attached Korean verb phrase for a relation TYPE (allomorph-correct josa).
    Relation-type surface, not per-entity — the closed inventory a definitional tail draws from."""
    j_i = obj + ("이" if _batchim(obj) else "가")
    j_ro = obj + ("으로" if _batchim(obj) else "로")
    return {
        "결과": f"{j_ro} 이어집니다", "causes": f"{j_ro} 이어집니다",
        "발견자": f"{j_i} 발견했습니다", "발견": f"{j_i} 발견했습니다",
        "원인": f"{obj} 때문에 생깁니다",
        "located_in": f"{j_i} 있는 곳에 위치합니다", "country": f"{j_i} 속한 나라입니다",
        "인구": f"인구는 {obj}명입니다", "면적": f"면적은 {obj}입니다",
        "used_for": f"{j_ro} 쓰입니다", "created_by": f"{j_i} 만들었습니다",
        "part_of": f"{j_i} 속한 상위 개념입니다",
    }.get(pred)


def answer(query: str,
           facts_about: Callable[[str], list[tuple[str, str, str]]]) -> dict[str, Any] | None:
    """Definitional entry point: extract the topic concept from `query` and compose from its
    activation field. Returns None when no candidate is a graph-known concept — so an engage/felt
    lane can safely use a truthy result as the 'this is a knowledge question' signal (grounded,
    not an emotion-word list)."""
    try:
        from packages.graph_scale.answer_bridge import _subject_candidates
        cands = _subject_candidates(query)
    except Exception:
        cands = []
    for subj in cands[:3]:
        subj = (subj or "").strip()
        if not subj:
            continue
        r = compose(query, subj, facts_about)
        if r and r.get("answer"):
            return r
    return None


def compose(query: str, anchor: str,
            facts_about: Callable[[str], list[tuple[str, str, str]]],
            *, intent_preds: tuple[str, ...] = (),
            sa_kwargs: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Compose a grounded, multi-hop answer for `anchor` from the activation field.
    Returns None (defer) when the field has nothing cleanly speakable. `sa_kwargs` lets the
    evolution harness score a candidate spreading-activation genome; live callers omit it."""
    sg = spread(anchor, facts_about, intent_preds=intent_preds, **(sa_kwargs or {}))
    props = sg.properties.get(anchor, [])
    definition = _dominant_def(anchor, props)

    sentences: list[str] = []
    used: list[tuple[str, str, str]] = []
    steps: list[dict[str, Any]] = []

    # 1) INTENT-focused lead: the brightest edge whose predicate is the asked relation.
    intent_edge = None
    if intent_preds:
        cand = [(s, p, o, d) for (s, p, o, d) in sg.edges
                if s == anchor and p in intent_preds and _clean_concept(o)]
        cand.sort(key=lambda x: -x[3])
        intent_edge = cand[0] if cand else None
    if intent_edge:
        s, p, o, _d = intent_edge
        rel_ko = _REL_KO.get(p, "관련된 것은")
        sentences.append(f"{anchor}의 {rel_ko} {o}입니다.")
        used.append((s, p, o))
        steps.append({"type": "intent_edge", "fact": f"({anchor}, {p}, {o})"})
        # DEEP follow-on: describe the target from ITS OWN facts (the 2nd hop) — the difference
        # between a lookup and understanding. Only speak a CLEAN Korean def / kind, never junk.
        tgt_def = _dominant_def(o, sg.properties.get(o, []))
        tgt_kind = next(((pp, oo) for (ss, pp, oo, dd) in sg.edges
                         if ss == o and pp in ("is_a", "located_in", "part_of", "country")
                         and _clean_concept(oo) and oo != anchor), None)
        if tgt_def and tgt_def != o:
            sentences.append(f"{_topic(o)} {tgt_def}입니다.")
            steps.append({"type": "hop2_def", "fact": f"({o}, defined_as, {tgt_def[:30]})"})
        elif tgt_kind:
            kp, ko = tgt_kind
            sentences.append(f"{_topic(o)} {ko}에 위치합니다." if kp in ("located_in", "country")
                             else f"{_topic(o)} {ko}입니다.")
            steps.append({"type": "hop2_kind", "fact": f"({o}, {kp}, {ko})"})

    # 2) DEFINITIONAL lead (no intent, or intent unmet): dominant def + brightest clean relations.
    if not sentences and definition:
        sentences.append(f"{_topic(anchor)} {definition}입니다.")
        steps.append({"type": "definition", "fact": f"({anchor}, defined_as, {definition[:30]})"})
        rels = [(s, p, o, d) for (s, p, o, d) in sg.edges
                if s == anchor and _tail_clause(p, o) and _clean_concept(o)]
        rels.sort(key=lambda x: -x[3])
        conj = ["그리고", "또한", "한편"]
        seen: set[tuple[str, str]] = set()
        n = 0
        for s, p, o, _d in rels:
            if (p, o) in seen or n >= 3:
                continue
            seen.add((p, o))
            sentences.append(f"{conj[min(n, 2)]} {_tail_clause(p, o)}.")
            steps.append({"type": "relation", "fact": f"({anchor}, {p}, {o})"})
            used.append((s, p, o))
            n += 1


    # defined_as→depression (English) + is_a→Disease). Speak the Koreanized class so the concept

    # empathy/engage lane. Never invents — only speaks a class the graph actually asserts.
    if not sentences:
        isa = next((_concept_ko(oo) for (ss, pp, oo, dd) in sg.edges
                    if ss == anchor and pp in ("is_a", "instance_of", "subclass_of")
                    and _concept_ko(oo)), None)
        if isa:
            sentences.append(f"{_topic(anchor)} {isa}의 하나입니다.")
            steps.append({"type": "is_a_fallback", "fact": f"({anchor}, is_a, {isa})"})

    if not sentences:
        return None
    answer = " ".join(sentences)
    result = {
        "answer": answer,
        "answer_kind": "graph_native_spread",
        "confidence": 0.85,
        "reasoning_certificate": {
            "derivation_kind": "spreading_activation",
            "anchor_concept": anchor,
            "steps": steps,
            "evidence_concepts": [anchor] + [o for (_s, _p, o) in used],
            "confidence": 0.85,
            "confidence_basis": "activation_ranked_stored_facts",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
    }
    # MEMBRANE signal plumbing (flag-gated, default OFF). Additive: when ATANOR_MEMBRANE_LIVE=1 this
    # attaches result["_membrane_signals"] from the REAL ActivatedSubgraph `sg` (computed above and
    # otherwise discarded) so the conformal gate reads real signals instead of the 0.85 constant.
    # When the flag is unset it is a pure no-op returning `result` unchanged (byte-identical).
    try:
        from packages.conformal_gate.live_wiring import attach_membrane_signals
        attach_membrane_signals(result, subgraph=sg, anchor=anchor)
    except Exception:
        pass
    return result
