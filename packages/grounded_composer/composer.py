# -*- coding: utf-8 -*-
"""Grounded Composer v1 — graph-native multi-fact utterance generation (roadmap P2).

The single-fact bridge answers "X Y." — one template, one triple. Language-model
COMPLETION means composing several stored facts into one fluent paragraph. This module
does that with the GCG + contract:

 (bones) = the facts, verbatim: every content span in the output is the exact
 subject/object string of a stored triple.
 (flesh) = a deterministic discourse plan (identification -> elaboration) plus a
 closed connective whitelist (//) and the LAD particle layer.

HALLUCINATION-SAFE BY CONSTRUCTION: the output vocabulary is exactly
{template constants} ∪ {connective whitelist} ∪ {verbatim fact strings}. There is no
free-text generation step that COULD invent content — the safety property is testable
as token containment, and the test suite asserts it.
"""
from __future__ import annotations

import os

from dataclasses import dataclass, field
from typing import Any

# identification first, then elaboration, then origin/agency, then consequence —

# LOGICAL-RELATION DIVERSITY × DISCOURSE PATTERNS, not from more fact tonnage).
_PRED_ORDER = ("defined_as", "is_a", "상위개념", "capital", "capital_of", "located_in",
               "country", "currency", "구성요소", "author", "저자", "설립자", "발견자",
               "최고경영자", "설립", "원인", "결과")
# closed connective whitelist (the ONLY non-template, non-fact tokens allowed).
# The learned discourse model RANKS within this list from corpus statistics —
# it chooses among approved tokens, it can never add one (testable closure).
_CONNECTIVES = ("또한", "그리고", "한편", "이와 함께", "특히", "더불어", "아울러", "이어서",
                "그래서", "이 때문에", "즉", "결국", "하지만", "그러나")
# contrast/commonality connectives for the comparison schema — same closed-vocabulary rule
_CONTRAST_CONNECTIVES = ("반면", "둘 다")
# subject-dropped continuation frames: Korean elaboration reads naturally without

_KO_CONT: dict[str, str] = {
    "defined_as": "{o}이기도 합니다",
    "is_a": "{o}의 일종입니다",
    "capital": "수도는 {o}입니다",
    "capital_of": "{o}의 수도입니다",
    "located_in": "{o}에 위치합니다",
    "country": "나라는 {o}입니다",
    "author": "저자는 {o}입니다",
    # relation-diversity tranche: the new logical edges SPEAK — each mined or
    # profiled relation has a voice, so richer graphs read as richer prose
    "저자": "{o}이(가) 썼습니다",
    "설립자": "{o}이(가) 세웠습니다",
    "발견자": "{o}이(가) 발견했습니다",
    "최고경영자": "최고경영자는 {o}입니다",
    "설립": "{o}에 세워졌습니다",
    "구성요소": "{o}(으)로 이루어져 있습니다",
    "상위개념": "{o}의 일부입니다",
    "원인": "{o} 때문에 생깁니다",
    "결과": "{o}(으)로 이어집니다",
    "currency": "통화는 {o}입니다",
}
_KO_LEAD: dict[str, str] = {
    "defined_as": "{s_topic} {o}입니다",
    "is_a": "{s_topic} {o}의 일종입니다",
    "capital": "{s}의 수도는 {o}입니다",
    "capital_of": "{s_topic} {o}의 수도입니다",
    "located_in": "{s_topic} {o}에 위치합니다",
    "country": "{s}의 나라는 {o}입니다",
    "author": "{s}의 저자는 {o}입니다",
    "저자": "{s}의 저자는 {o}입니다",
    "설립자": "{s_topic} {o}이(가) 세웠습니다",
    "발견자": "{s_topic} {o}이(가) 발견했습니다",
    "최고경영자": "{s}의 최고경영자는 {o}입니다",
    "설립": "{s_topic} {o}에 세워졌습니다",
    "구성요소": "{s_topic} {o}(으)로 이루어져 있습니다",
    "상위개념": "{s_topic} {o}의 일부입니다",
    "원인": "{s_topic} {o} 때문에 생깁니다",
    "결과": "{s_topic} {o}(으)로 이어집니다",
    "currency": "{s}의 통화는 {o}입니다",
}



# fact string; the only added tokens are these frames and connectives. No article
# guessing on the object (that would be invented content) — the stored label stands.
# English can't drop the subject like Korean, so continuations carry their own
# "It ..." — the connective is prepended separately.
_EN_CONNECTIVES = ("Additionally,", "Additionally,", "Additionally,")

# LEARNED English connectives (register harvest, 2026-07-17). The static triple above is one
# word three times — the measured "dictionary taste". The harvested bank
# (data/registers/english_register_bank.json, english.stackexchange.com CC BY-SA, 54k
# score>=5 answers) supplies community-validated discourse markers instead. Two rules:
#   * ADDITIVE class only. A connective before a NEW fact must not promise restatement
#     ("in other words,"), contrast ("that said,") or exemplification ("for example,") —
#     discourse markers carry meaning, and the wrong one is a small lie about what follows.
#   * Deterministic: chosen by crc32(subject)+position, so the same question always gets the
#     same answer while different subjects stop sounding identical. No RNG in the voice.
# Delete the bank file and the lane reverts to the static tuple — same reversibility contract
# as every other data asset today.
# NOT in the set: "similarly"/"likewise" assert the new fact PARALLELS the previous one —
# false for heterogeneous facts (a reptile vs. lives-in-rivers are not similar). Caught on
# the first wiring probe; pure addition only.
_EN_ADDITIVE = {"also", "additionally", "moreover", "furthermore", "in addition", "in fact",
                "beyond that", "on top of that"}
_EN_LEARNED_CONNS: tuple[str, ...] | None = None


def _en_learned_connectives() -> tuple[str, ...]:
    global _EN_LEARNED_CONNS
    if _EN_LEARNED_CONNS is None:
        conns: list[str] = []
        try:
            import json as _json
            from pathlib import Path as _Path

            bank_path = _Path(__file__).resolve().parents[2] / "data" / "registers" / \
                "english_register_bank.json"
            bank = _json.loads(bank_path.read_text(encoding="utf-8"))
            for row in bank.get("transitions", []):
                span = str(row.get("span") or "").strip()
                if span.rstrip(",").lower() in _EN_ADDITIVE and row.get("posts", 0) >= 60:
                    conns.append(span[0].upper() + span[1:])
        except Exception:
            conns = []
        _EN_LEARNED_CONNS = tuple(conns) or _EN_CONNECTIVES
    return _EN_LEARNED_CONNS


def _en_pick_connective(subject: str, position: int) -> str:
    conns = _en_learned_connectives()
    import zlib as _zlib
    return conns[(_zlib.crc32(subject.encode("utf-8")) + position) % len(conns)]
_EN_LEAD: dict[str, str] = {
    "defined_as": "{s} is {o}",
    "is_a": "{s} is a kind of {o}",
    "capital": "The capital of {s} is {o}",
    "capital_of": "{s} is the capital of {o}",
    "located_in": "{s} is located in {o}",
    "country": "{s} is in {o}",
    "author": "{s} was written by {o}",
    "currency": "The currency of {s} is {o}",
}
_EN_CONT: dict[str, str] = {
    "defined_as": "it is also {o}",
    "is_a": "it is a kind of {o}",
    "located_in": "it is located in {o}",
    "capital": "its capital is {o}",
    "country": "it is in {o}",
    "author": "it was written by {o}",
    "currency": "its currency is {o}",
}


@dataclass
class ComposedAnswer:
    answer: str
    facts_used: list[tuple[str, str, str]] = field(default_factory=list)
    connectives_used: list[str] = field(default_factory=list)

    def certificate(self) -> dict[str, Any]:
        return {
            "derivation_kind": "grounded_composition",
            "anchor_concept": {"label": self.facts_used[0][0] if self.facts_used else ""},
            "steps": [{"type": "triple", "fact": f"{s} {p} {o}"} for s, p, o in self.facts_used],
            "evidence_concepts": sorted({t for s, _p, o in self.facts_used for t in (s, o)}),
            "confidence": 0.88,
            "confidence_basis": "curated_structured_triples_verbatim_composition",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "inferred": False,
                           "composition_vocabulary_closed": True},
        }


def _ko_topic_particle(label: str) -> str:
    from packages.lad_morphology import topic

    return topic(label)[len(label):]


# Korean plain-declarative sentence terminals: an object ending in one of these


_CLAUSE_TERMINALS = ("다", "요", "음", "임", "됨", "네", "지", "라", "함")


def _is_clause(text: str) -> bool:
    """True when a stored object reads as a finished sentence rather than a noun
 phrase — either it ends in a declarative terminal, or it carries its own
 subject (a / topic particle before the tail) marking an embedded clause."""
    t = (text or "").strip().rstrip(".。！!?？").strip()
    if not t:
        return False
    if t.endswith(_CLAUSE_TERMINALS):
        return True

    import re as _re

    return bool(_re.search(r"[가-힣]+[은는]\s", t))


def _resolve_josa(sentence: str) -> str:
    """Resolve placeholders the frames leave when the slot filler's final
 syllable decides the particle: X(), X(). LAD layer, data-driven."""
    import re as _re

    from packages.lad_morphology import has_batchim

    def _iga(m: "_re.Match[str]") -> str:
        w = m.group(1)
        return w + ("이" if has_batchim(w[-1]) else "가")

    def _euro(m: "_re.Match[str]") -> str:
        w = m.group(1)
        last = w[-1]
        return w + ("로" if (not has_batchim(last)) or (ord(last) - 0xAC00) % 28 == 8 else "으로")

    sentence = _re.sub(r"([가-힣A-Za-z0-9]+)이\(가\)", _iga, sentence)
    sentence = _re.sub(r"([가-힣A-Za-z0-9]+)\(으\)로", _euro, sentence)
    return sentence


def compose_from_facts(subject: str, facts: list[tuple[str, str, str]],
                       language: str = "ko", max_facts: int = 4) -> ComposedAnswer | None:
    """Compose a fluent multi-fact answer. Returns None when fewer than TWO usable
    facts exist — single-fact answers stay on the precise single-template path."""
    if language not in ("ko", "en"):
        return None
    # dual-route (S2.5b, live wiring): for ENGLISH answers try the idiom route first — a mined human
    # frame filled from the verified facts. Grounded frame output leads the answer; on any failure we
    # fall through to the existing composer unchanged (zero-regression flag, default ON for en).
    if language == "en" and os.environ.get("ATANOR_DUAL_ROUTE", "1") != "0" and facts:
        try:
            from packages.grounded_composer.dual_route import realize_dual
            usable = [[s, p, o] for s, p, o in facts if p not in ("alias", "sense")]
            bones = usable[:1]
            if len(usable) == 1:                         # multi-fact answers keep the richer legacy path
                dr = realize_dual(bones)
                if dr.route in ("frame", "generic") and dr.grounded and dr.text:
                    return ComposedAnswer(answer=dr.text + " (source: curated knowledge graph)",
                                          facts_used=[tuple(bones[0])], connectives_used=[])
        except Exception:
            pass                                             # any wiring issue -> legacy path, no regression
    lead = _KO_LEAD if language == "ko" else _EN_LEAD
    cont = _KO_CONT if language == "ko" else _EN_CONT
    conns = _CONNECTIVES if language == "ko" else _EN_CONNECTIVES
    source = " (출처: 큐레이션 지식그래프)" if language == "ko" else " (source: curated knowledge graph)"
    # one fact per predicate, discourse-ordered, alias/sense excluded (they have their
    # own dedicated answer paths: substitution hop and enumeration).
    by_pred: dict[str, tuple[str, str, str]] = {}
    for s, p, o in facts:
        if p in ("alias", "sense"):
            continue
        if p not in by_pred:
            by_pred[p] = (s, p, o)
    ordered = [by_pred[p] for p in _PRED_ORDER if p in by_pred]
    ordered += [f for p, f in by_pred.items() if p not in _PRED_ORDER]

    # drop a fact whose object already appears verbatim inside an earlier fact's object
    deduped: list[tuple[str, str, str]] = []
    for f in ordered:
        if any(f[2] and f[2] in prev[2] for prev in deduped):
            continue
        deduped.append(f)
    ordered = deduped[:max_facts]
    if len(ordered) < 2:
        return None


    # verbatim-grounded; the flat connective chain below remains the fallback
    # whenever the realizer declines. Kill-switch: ATANOR_RECURSIVE_REALIZER=0.
    try:
        import os as _os

        if language == "ko" and _os.getenv("ATANOR_RECURSIVE_REALIZER", "1") != "0":
            from .recursive_realizer import realize

            _r = realize(subject, ordered, max_modifiers=2)
            if _r is not None and len(_r.facts_used) >= 3:
                _ans = _r.text + source
                return ComposedAnswer(answer=_resolve_josa(_ans),
                                      facts_used=_r.facts_used,
                                      connectives_used=_r.constructions)
    except Exception:
        pass
    # PHASE-COHERENT FLOW (softness in utterance, owner directive): keep the
    # identity lead first, then walk the remaining facts nearest-first in the
    # trained phase space so the discourse moves in a coherent path. Content is
    # untouched — only ORDER changes; degrades to static order without a space.
    try:
        from .phase_flow import flow_order

        ordered = [ordered[0]] + flow_order(ordered[0], ordered[1:])
    except Exception:
        pass

    sentences: list[str] = []
    connectives: list[str] = []
    used: list[tuple[str, str, str]] = []
    for s, p, o in ordered:
        if not sentences:
            frame = lead.get(p)
            if frame is None:  # unknown lead predicate: never improvise a frame
                continue
            topic = s + _ko_topic_particle(s) if language == "ko" else s
            sentences.append(frame.format(s=s, o=o, s_topic=topic) + ".")
            used.append((s, p, o))
        else:
            frame = cont.get(p)
            if frame is None:  # unknown predicate: keep it out rather than improvise
                continue
            conn = conns[min(len(connectives), len(conns) - 1)]
            if language == "en":
                # learned register bank (StackExchange harvest) — the English mirror of the
                # Korean learned-discourse branch below, same additive-only rule, same
                # static-tuple fallback when the bank is absent.
                conn = _en_pick_connective(subject, len(connectives))
            if language == "ko":
                # learned discourse model (corpus-ranked, closed vocabulary) —
                # falls back to the static tuple when no stats are trained
                try:
                    from .discourse_model import pick_connective

                    learned = pick_connective(len(connectives),
                                              connectives[-1] if connectives else None)




                    _additive = ("또한", "그리고", "한편", "이와 함께", "특히",
                                 "더불어", "아울러", "이어서")
                    if learned and learned in _additive:
                        conn = learned
                except Exception:
                    pass
                # phase-distance connective (closed vocabulary only): objects


                # positional/learned choice above stands.
                try:
                    from .phase_flow import connective_hint

                    _hint = connective_hint(used[-1][2], o)
                    if _hint == "near" and conn == "한편":
                        conn = "또한"
                    elif _hint == "far":
                        conn = "한편"
                except Exception:
                    pass
            connectives.append(conn)
            sentences.append(f"{conn} {frame.format(o=o)}.")
            used.append((s, p, o))
    if len(sentences) < 2:
        return None
    answer = " ".join(sentences) + source
    if language == "ko":
        answer = _resolve_josa(answer)
    return ComposedAnswer(answer=answer, facts_used=used, connectives_used=connectives)


# ── the FLUENCY REALISER (M-B1/M-B2): grounded multi-sentence DISCOURSE with a per-sentence trace ──
@dataclass
class GroundedDiscourse:
    """The fluency realiser's output: >= 2 sentences of discourse, EACH one rendered from exactly ONE
    verified stored triple, carrying the per-sentence grounding trace so faithfulness is inspectable
    (M-B1/M-B2 — the OAM 'fluency register' capability). Hallucination-safe by the SAME token-
    containment property as :class:`ComposedAnswer`: the output vocabulary is exactly
    {template constants} ∪ {additive-connective whitelist} ∪ {verbatim fact strings}, so no sentence
    can carry content that is not a stored fact (작화0 by construction, not by hope)."""
    answer: str
    # (sentence_text, source_triple) for EACH rendered sentence — the grounding trace
    sentences: list[tuple[str, tuple[str, str, str]]] = field(default_factory=list)
    facts_used: list[tuple[str, str, str]] = field(default_factory=list)
    connectives_used: list[str] = field(default_factory=list)

    def certificate(self) -> dict[str, Any]:
        return {
            "derivation_kind": "grounded_discourse",
            "anchor_concept": {"label": self.facts_used[0][0] if self.facts_used else ""},
            "steps": [{"type": "triple", "sentence": snt, "fact": f"{s} {p} {o}"}
                      for snt, (s, p, o) in self.sentences],
            "evidence_concepts": sorted({t for s, _p, o in self.facts_used for t in (s, o)}),
            "confidence": 0.88,
            "confidence_basis": "verbatim_grounded_multi_sentence_composition",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "inferred": False,
                           "composition_vocabulary_closed": True},
        }


def realize_grounded_discourse(subject: str,
                               grounded_facts: list[tuple[str, str, str]],
                               language: str = "en",
                               source: bool = True,
                               max_sentences: int = 4) -> GroundedDiscourse | None:
    """FLUENCY REALISER — compose >= 2 sentences of grounded discourse from an ORDERED list of already
    VERIFIED facts (the caller puts the primary / answer-bearing fact FIRST; identification-then-
    elaboration also works — order is the caller's editorial choice). Each sentence is one stored
    triple rendered through a fixed frame; the ONLY non-fact tokens are the closed template plus the
    additive-connective whitelist, so the result is hallucination-safe by token containment.

    CONTRACT (the caller's duty): every ``(s, p, o)`` in ``grounded_facts`` is already membrane-
    verified / stored — this function RENDERS, it never grounds. It returns ``None`` below two
    realisable relations: a single fact stays on the precise single-template path and is NEVER padded
    with an ungrounded sentence to reach a length (a padded sentence would be fabrication, not
    fluency). No-LLM, deterministic given the input order."""
    if language not in ("en", "ko"):
        return None
    lead = _EN_LEAD if language == "en" else _KO_LEAD
    cont = _EN_CONT if language == "en" else _KO_CONT
    src = ("" if not source else
           " (source: curated knowledge graph)" if language == "en" else " (출처: 큐레이션 지식그래프)")
    # one sentence per predicate, caller order preserved; alias/sense never compose (own answer paths)
    seen: set[str] = set()
    ordered: list[tuple[str, str, str]] = []
    for s, p, o in grounded_facts:
        if p in ("alias", "sense") or p in seen:
            continue
        seen.add(p)
        ordered.append((s, p, o))
    sentences: list[str] = []
    grounding: list[tuple[str, tuple[str, str, str]]] = []
    used: list[tuple[str, str, str]] = []
    conns: list[str] = []
    for s, p, o in ordered[:max_sentences]:
        if not sentences:
            frame = lead.get(p)
            if frame is None:                     # never improvise a frame for an unknown predicate
                continue
            topic = (s + _ko_topic_particle(s)) if language == "ko" else s
            snt = frame.format(s=s, o=o, s_topic=topic) + "."
        else:
            frame = cont.get(p)
            if frame is None:
                continue
            conn = (_en_pick_connective(subject, len(conns)) if language == "en"
                    else _CONNECTIVES[min(len(conns), len(_CONNECTIVES) - 1)])
            conns.append(conn)
            snt = f"{conn} {frame.format(o=o)}."
        if language == "ko":
            snt = _resolve_josa(snt)
        sentences.append(snt)
        grounding.append((snt, (s, p, o)))
        used.append((s, p, o))
    if len(sentences) < 2:                         # below the discourse floor -> defer (never pad)
        return None
    answer = " ".join(sentences) + src
    return GroundedDiscourse(answer=answer, sentences=grounding, facts_used=used,
                             connectives_used=conns)


_PARA_GROUPS: tuple[tuple[str, ...], ...] = (
    ("defined_as", "is_a", "상위개념", "구성요소", "capital", "located_in", "country"),
    ("설립자", "설립", "저자", "author", "발견자", "최고경영자", "capital_of"),
    ("원인", "결과", "used_for"),
)


def compose_narrative(subject: str, facts: list[tuple[str, str, str]],
                      language: str = "ko") -> ComposedAnswer | None:
    """+ v3 first slice — a multi-PARAGRAPH answer with a arc.

 ¶ identity/composition, ¶ origin/agency, ¶ causality/use — each
 paragraph composed by the same closed-vocabulary machinery — and ¶ a
 -summary that REUSES the identity object verbatim. Fires only when at
 least two paragraph groups have material; otherwise the caller keeps the
 single-paragraph composer (adaptive depth, never padding)."""
    if language != "ko":
        return None
    by_pred: dict[str, tuple[str, str, str]] = {}
    for s, p, o in facts:
        if p not in ("alias", "sense") and p not in by_pred:
            by_pred[p] = (s, p, o)
    paragraphs: list[str] = []
    used: list[tuple[str, str, str]] = []
    conns: list[str] = []
    for group in _PARA_GROUPS:
        group_facts = [by_pred[p] for p in group if p in by_pred]
        if not group_facts:
            continue
        comp = compose_from_facts(subject, group_facts, language="ko")
        if comp is not None:
            paragraphs.append(_strip_source(comp.answer))
            used.extend(comp.facts_used)
            conns.extend(comp.connectives_used)
        elif len(group_facts) == 1 and paragraphs:
            # a one-fact paragraph still contributes as a lead sentence
            s, p, o = group_facts[0]
            frame = _KO_LEAD.get(p)
            if frame:
                topic = s + _ko_topic_particle(s)
                paragraphs.append(_resolve_josa(frame.format(s=s, o=o, s_topic=topic) + "."))
                used.append((s, p, o))
    if len(paragraphs) < 2:
        return None





    head = by_pred.get("defined_as") or by_pred.get("is_a")
    if head and not _is_clause(head[2]):
        closer = f"즉, {subject + _ko_topic_particle(subject)} {head[2]}"
        closer += "의 일종입니다." if head[1] == "is_a" else "입니다."
        paragraphs.append(_resolve_josa(closer))
        conns.append("즉")
    answer = "\n\n".join(paragraphs) + " (출처: 큐레이션 지식그래프)"
    return ComposedAnswer(answer=answer, facts_used=used, connectives_used=conns)


def _strip_source(text: str) -> str:
    import re as _re

    return _re.sub(r"\s*\((?:출처|source)[^)]*\)\s*$", "", text).rstrip()


def _pick_lead(facts: list[tuple[str, str, str]],
               avoid: tuple[str, str, str] | None = None) -> tuple[str, str, str] | None:
    """Highest-priority identifying fact for a subject, preferring one that DIFFERS
    from `avoid` (so a contrast never contrasts a thing with itself)."""
    by_pred: dict[str, tuple[str, str, str]] = {}
    for s, p, o in facts:
        if p not in ("alias", "sense") and p not in by_pred:
            by_pred[p] = (s, p, o)
    ordered = [by_pred[p] for p in _PRED_ORDER if p in by_pred]
    ordered += [f for p, f in by_pred.items() if p not in _PRED_ORDER]
    for f in ordered:
        if avoid is None or (f[1], f[2]) != (avoid[1], avoid[2]):
            return f
    return ordered[0] if ordered else None


def compose_comparison(a: str, b: str,
                       facts_a: list[tuple[str, str, str]],
                       facts_b: list[tuple[str, str, str]],
                       common: tuple[str, list[tuple[str, str, str]],
                                     list[tuple[str, str, str]]] | None = None,
                       language: str = "ko") -> ComposedAnswer | None:
    """Contrast schema ( B1): identify A, contrast B (), then the grounded
 commonality ( <shared ancestor>) when the taxonomy ladders meet. Same GCG
 closure: every content span is a verbatim stored label."""
    fa0 = _pick_lead(facts_a)
    fb0 = _pick_lead(facts_b, avoid=fa0)
    if fa0 is None or fb0 is None:
        return None
    # ENGLISH ARM (2026-07-17). This returned None for English on the reasoning that EN parity was
    # a separate lane and frames must not be improvised. But _EN_LEAD already exists and the
    # single-paragraph composer uses it — the closure rule binds CONTENT spans (every one is a

    # on the Korean side. Leaving it None was not caution, it was a hole: measured, "How is coffee
    # different from tea?" fell to base_brain and answered "Tear Out The Heart was a five-piece
    # metalcore band… Steampipe Alley is a children's television program…" — a fuzzy match on 'tea'.
    if language != "ko":
        lead_a, lead_b = _EN_LEAD.get(fa0[1]), _EN_LEAD.get(fb0[1])
        if lead_a is None or lead_b is None:
            return None
        sentences = [
            lead_a.format(s=a, o=fa0[2], s_topic=a) + ".",
            "By contrast, " + lead_b.format(s=b, o=fb0[2], s_topic=b) + ".",
        ]
        used, connectives = [fa0, fb0], ["By contrast"]
        if common is not None:
            anc, chain_a, chain_b = common
            sentences.append(f"Both are a kind of {anc} — that much they share.")
            connectives.append("Both are")
            used.extend(chain_a)
            used.extend(chain_b)
        return ComposedAnswer(answer=" ".join(sentences) + " (sources: curated knowledge graph)",
                              facts_used=used, connectives_used=connectives)
    lead_a = _KO_LEAD.get(fa0[1])
    lead_b = _KO_LEAD.get(fb0[1])
    if lead_a is None or lead_b is None:
        return None

    sentences = [
        lead_a.format(s=a, o=fa0[2], s_topic=a + _ko_topic_particle(a)) + ".",
        "반면 " + lead_b.format(s=b, o=fb0[2], s_topic=b + _ko_topic_particle(b)) + ".",
    ]
    used = [fa0, fb0]
    connectives = ["반면"]
    if common is not None:
        anc, chain_a, chain_b = common
        sentences.append(f"둘 다 {anc}의 일종이라는 공통점이 있습니다.")
        connectives.append("둘 다")
        used.extend(chain_a)
        used.extend(chain_b)
    answer = " ".join(sentences) + " (출처: 큐레이션 지식그래프)"
    composed = ComposedAnswer(answer=answer, facts_used=used, connectives_used=connectives)
    return composed



# direct used_for/capable_of/has_part facts plus the ones the taxonomy ladder
# passes down (inherited via packages.graph_scale.chain_reasoner.inherited_facts).
_KO_PURPOSE_LEAD: dict[str, str] = {
    "used_for": "{s_topic} {o}에 쓰입니다",
    "capable_of": "{s_topic} '{o}'{i_ga} 가능합니다",
    "has_part": "{s}에는 {o}{i_ga} 있습니다",
}
_KO_PURPOSE_CONT: dict[str, str] = {
    "used_for": "{o}에도 쓰입니다",
    "capable_of": "'{o}'{i_ga} 가능합니다",
    "has_part": "{o}{i_ga} 있습니다",
}
# English twins of the purpose frames (2026-07-17). Frames are scaffolding; every content span
# ({s}, {o}) is still a verbatim stored label, so the GCG closure is unchanged.
_EN_PURPOSE_LEAD: dict[str, str] = {
    "used_for": "{s} is used for {o}",
    "capable_of": "{s} can {o}",
    "has_part": "{s} has {o}",
}
_EN_PURPOSE_CONT: dict[str, str] = {
    "used_for": "it is also used for {o}",
    "capable_of": "it can also {o}",
    "has_part": "it also has {o}",
}


def _ko_subject_particle(label: str) -> str:
    from packages.lad_morphology import subject

    return subject(label)[len(label):]


def compose_purpose(subject: str,
                    direct: list[tuple[str, str, str]],
                    inherited: list[tuple[list[tuple[str, str, str]], tuple[str, str, str]]] = (),
                    language: str = "ko", max_facts: int = 4) -> ComposedAnswer | None:
    """Purpose paragraph over stored used_for/capable_of/has_part facts. Direct facts
 lead; inherited ones follow WITH their taxonomy source named (X ) so
 the inference is visible, never smuggled."""
    if language != "ko":
        # ENGLISH ARM (2026-07-17): same schema, English frames, same closure — and inherited
        # facts still NAME the ancestor they came from ("as a kind of X"), so the inference stays
        # visible rather than smuggled, exactly as the Korean branch requires.
        _own = [(s, p, o) for s, p, o in direct if p in _EN_PURPOSE_LEAD]
        _seen = {(p, o) for _s, p, o in _own}
        _inh = [(c, e) for c, e in inherited
                if c and e[1] in _EN_PURPOSE_LEAD and (e[1], e[2]) not in _seen]
        if not _own and not _inh:
            return None
        _sent: list[str] = []
        _conn: list[str] = []
        _used: list[tuple[str, str, str]] = []
        for s, p, o in _own[:max_facts]:
            frame = _EN_PURPOSE_LEAD[p] if not _sent else _EN_PURPOSE_CONT[p]
            if _sent:
                _conn.append("also")
            _sent.append(frame.format(s=subject, o=o) + ".")
            _used.append((s, p, o))
        for chain, (s, p, o) in _inh[: max(0, max_facts - len(_sent))]:
            kind = chain[-1][2]
            frame = _EN_PURPOSE_CONT[p] if _sent else _EN_PURPOSE_LEAD[p]
            if _sent:
                _conn.append("also")
            _sent.append(f"As a kind of {kind}, " + frame.format(s=subject, o=o) + ".")
            _used.extend(chain)
            _used.append((s, p, o))
        if not _sent:
            return None
        # sentence case: the continuation frames start with a pronoun ("it also has …"), which is
        # correct mid-clause but must be capitalised once it stands as its own sentence.
        _sent = [x[:1].upper() + x[1:] if x else x for x in _sent]
        return ComposedAnswer(answer=" ".join(_sent) + " (sources: curated knowledge graph)",
                              facts_used=_used, connectives_used=_conn)
    own = [(s, p, o) for s, p, o in direct if p in _KO_PURPOSE_LEAD]
    seen_po = {(p, o) for _s, p, o in own}
    inh = [(chain, edge) for chain, edge in inherited
           if chain and edge[1] in _KO_PURPOSE_LEAD and (edge[1], edge[2]) not in seen_po]
    if not own and not inh:
        return None

    sentences: list[str] = []
    connectives: list[str] = []
    used: list[tuple[str, str, str]] = []
    for s, p, o in own[:max_facts]:
        frame = _KO_PURPOSE_LEAD[p] if not sentences else _KO_PURPOSE_CONT[p]
        prefix = "" if not sentences else "또한 "
        if prefix:
            connectives.append("또한")
        sentences.append(prefix + frame.format(
            s=subject, o=o, s_topic=subject + _ko_topic_particle(subject),
            i_ga=_ko_subject_particle(o)) + ".")
        used.append((s, p, o))
    for chain, (s, p, o) in inh[: max(0, max_facts - len(sentences))]:
        kind = chain[-1][2]  # the ancestor the property actually comes from
        frame = _KO_PURPOSE_CONT[p]
        prefix = "" if not sentences else "또한 "
        if prefix:
            connectives.append("또한")
        sentences.append(
            prefix + f"{kind}의 일종으로서 " + frame.format(
                s=subject, o=o, s_topic=subject + _ko_topic_particle(subject),
                i_ga=_ko_subject_particle(o)) + ".")
        used.extend(chain)
        used.append((s, p, o))
    if not sentences:
        return None
    # a lone continuation frame has no subject — re-lead it
    if len(used) >= 1 and not own and sentences:
        first_chain, first_edge = inh[0]
        s0, p0, o0 = first_edge
        sentences[0] = f"{subject + _ko_topic_particle(subject)} {first_chain[-1][2]}의 일종으로서 " + \
            _KO_PURPOSE_CONT[p0].format(o=o0, i_ga=_ko_subject_particle(o0)) + "."
    answer = " ".join(sentences) + " (출처: 큐레이션 지식그래프)"
    return ComposedAnswer(answer=answer, facts_used=used, connectives_used=connectives)
