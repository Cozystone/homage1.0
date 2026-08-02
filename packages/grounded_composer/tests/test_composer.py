# -*- coding: utf-8 -*-
"""GCG + contract: identification-first ordering, closed connective whitelist,
and the hallucination-safety property — output vocabulary ⊆ templates ∪ connectives
∪ verbatim fact strings, asserted as token containment."""
from __future__ import annotations

import re

from packages.grounded_composer import compose_from_facts
from packages.grounded_composer.composer import _CONNECTIVES, _KO_CONT, _KO_LEAD

FACTS = [
    ("커피", "is_a", "음료"),
    ("커피", "defined_as", "커피나무 열매의 씨앗을 볶아 우려낸 음료"),
    ("커피", "located_in", "전 세계"),
]


def test_identification_comes_first_then_elaboration():
    r = compose_from_facts("커피", FACTS)
    assert r is not None
    # defined_as leads even though is_a arrived first in the list
    assert r.answer.startswith("커피는 커피나무 열매의 씨앗을 볶아 우려낸 음료입니다.")
    assert r.facts_used[0][1] == "defined_as"
    # the connective is chosen by the LEARNED discourse model within the closed
    # whitelist — assert the elaboration content, not one pinned connective
    assert "전 세계에 위치합니다." in r.answer
    assert any(f"{c} 전 세계에 위치합니다." in r.answer for c in _CONNECTIVES)


def test_redundant_elaboration_is_dropped():

    # appears as the head of the defined_as object, so the gate drops it.
    r = compose_from_facts("커피", FACTS)
    assert r is not None
    assert "또한 음료의 일종입니다." not in r.answer
    assert all(p != "is_a" for _s, p, _o in r.facts_used)


def test_single_fact_defers_to_single_template_path():
    assert compose_from_facts("커피", [("커피", "is_a", "음료")]) is None


def test_alias_and_sense_never_enter_composition():
    facts = [("비저", "sense", "마비저"), ("비저", "alias", "마비저"),
             ("비저", "is_a", "병명"), ("비저", "defined_as", "전염병의 하나")]
    r = compose_from_facts("비저", facts)
    assert r is not None
    assert "마비저" not in r.answer


def test_hallucination_safety_vocabulary_is_closed():
    r = compose_from_facts("커피", FACTS)
    assert r is not None
    body = r.answer.replace(" (출처: 큐레이션 지식그래프)", "")
    # remove template constants FIRST (longest chunks), then fact strings longest-first —

    chunks = []
    for frame in list(_KO_LEAD.values()) + list(_KO_CONT.values()):
        chunks += [c for c in re.split(r"\{[so](?:_topic)?\}", frame) if c.strip()]
    for c in sorted(set(chunks), key=len, reverse=True):
        body = body.replace(c, "")
    for term in sorted({t for s, _p, o in r.facts_used for t in (s, o)}, key=len, reverse=True):
        body = body.replace(term, "")
    for c in _CONNECTIVES:
        body = body.replace(c, "")
    # what remains may only be particles/punctuation/whitespace — no free content
    leftover = re.sub(r"[\s\.\,]", "", body)
    assert len(leftover) <= 4, f"unexpected free content: {leftover!r}"


def test_unknown_predicate_is_dropped_not_improvised():
    # located_in (not redundant with the definition) keeps two realizable facts
    # alive, so the weird predicate's exclusion is observable in a real answer.
    facts = [("커피", "defined_as", "볶은 씨앗 음료"), ("커피", "weird_pred", "이상한 값"),
             ("커피", "located_in", "전 세계")]
    r = compose_from_facts("커피", facts)
    assert r is not None
    assert "이상한 값" not in r.answer and "weird_pred" not in r.answer


def test_narrative_builds_multi_paragraph_arc():
    from packages.grounded_composer.composer import compose_narrative

    facts = [("테슬라", "defined_as", "미국의 전기자동차 제조사"),
             ("테슬라", "상위개념", "나스닥 100"),
             ("테슬라", "설립자", "마틴 에버하드"),
             ("테슬라", "설립", "2003년 7월 1일")]
    n = compose_narrative("테슬라", facts)
    assert n is not None
    paras = n.answer.split("\n\n")
    assert len(paras) >= 3
    assert paras[-1].startswith("즉,")           # closing reuses identity verbatim
    assert "미국의 전기자동차 제조사" in paras[-1]
    assert "마틴 에버하드가 세웠습니다" in n.answer  # josa resolved


def test_narrative_abstains_below_two_groups():
    from packages.grounded_composer.composer import compose_narrative

    facts = [("커피", "defined_as", "볶은 씨앗 음료"), ("커피", "is_a", "음료")]
    assert compose_narrative("커피", facts) is None  # one group only -> no padding


def test_english_comparison_and_purpose_compose_grounded():
    """Both returned None for English on the reasoning that "EN parity is a separate lane; never
 improvise frames". But _EN_LEAD already existed and the single-paragraph composer used it —
 the GCG closure binds CONTENT spans (still verbatim labels here); a connective is scaffolding,
 exactly as is on the Korean side. The hole was measurable: "How is coffee different from
 tea?" fell to base_brain and answered "Tear Out The Heart was a five-piece metalcore band…"
 """
    from packages.grounded_composer.composer import compose_comparison, compose_purpose

    r = compose_comparison(
        "coffee", "tea",
        [("coffee", "is_a", "beverage")], [("tea", "is_a", "herb")],
        ("beverage", [("coffee", "is_a", "beverage")], [("tea", "is_a", "beverage")]),
        language="en")
    assert r and "By contrast" in r.answer and "Both are a kind of beverage" in r.answer
    assert "coffee is a kind of beverage" in r.answer
    for _s, _p, o in r.facts_used:      # closure: every content span is a stored label
        assert o in r.answer

    r = compose_purpose(
        "thermometer",
        [("thermometer", "used_for", "measuring temperature")],
        [([("thermometer", "is_a", "measuring instrument")],
          ("measuring instrument", "capable_of", "give a reading"))],
        language="en")
    assert r and r.answer.startswith("Thermometer is used for measuring temperature.")
    # an inherited property must NAME the ancestor it came from — never smuggled
    assert "As a kind of measuring instrument" in r.answer

    # Korean unchanged
    rk = compose_comparison("커피", "차", [("커피", "is_a", "음료")], [("차", "is_a", "허브")],
                            None, language="ko")
    assert rk and "반면" in rk.answer


def test_fluency_realiser_composes_grounded_multi_sentence_discourse():
    """The FLUENCY REALISER (realize_grounded_discourse) — the OAM X5 'fluency register' capability.
    >= 2 sentences of grounded discourse, EACH one a verbatim VERIFIED triple, with a per-sentence
    grounding trace; the new 'currency' predicate has a wired utterance frame (fluency doctrine)."""
    from packages.grounded_composer import realize_grounded_discourse

    facts = [("Japan", "is_a", "Country"), ("Japan", "currency", "yen")]
    d = realize_grounded_discourse("Japan", facts, language="en")
    assert d is not None
    # multi-sentence discourse: identification then elaboration, each sentence its own grounded triple
    assert d.answer.startswith("Japan is a kind of Country.")
    assert "its currency is yen" in d.answer
    assert len(d.sentences) == 2
    # each sentence carries its object verbatim; the subject leads (continuations use the 'its'/'it'
    # coreference, subject dropped — the same continuation contract as compose_from_facts)
    for snt, (_s, _p, o) in d.sentences:
        assert o in snt
    assert d.sentences[0][0].startswith("Japan")           # the lead names the subject
    assert d.facts_used == facts
    # closure (작화0): strip frame constants + connective + verbatim fact tokens -> no free content
    body = d.answer.replace(" (source: curated knowledge graph)", "")
    from packages.grounded_composer.composer import _EN_LEAD, _EN_CONT
    chunks = []
    for frame in list(_EN_LEAD.values()) + list(_EN_CONT.values()):
        chunks += [c for c in re.split(r"\{[so](?:_topic)?\}", frame) if c.strip()]
    for c in sorted(set(chunks), key=len, reverse=True):
        body = body.replace(c, "")
    for term in sorted({t for s, _p, o in d.facts_used for t in (s, o)}, key=len, reverse=True):
        body = body.replace(term, "")
    for conn in d.connectives_used:
        body = body.replace(conn, "")
    leftover = re.sub(r"[\s\.\,]", "", body)
    assert len(leftover) <= 2, f"unexpected free content: {leftover!r}"
    # a single fact stays on the precise single-template path (never padded to a length)
    assert realize_grounded_discourse("Japan", [("Japan", "currency", "yen")], language="en") is None
