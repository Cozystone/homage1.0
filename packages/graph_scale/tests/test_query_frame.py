# -*- coding: utf-8 -*-
"""Query semantic frame — one structural parse fixes the wrong-subject + misroute classes."""

from __future__ import annotations

from packages.graph_scale.query_frame import parse


def test_genitive_relation_makes_X_the_subject():

    f = parse("물의 화학식은?")
    assert f.subject == "물" and f.relation == "화학식" and f.answer_type == "relation"
    f2 = parse("일본의 수도는?")
    assert f2.subject == "일본" and f2.relation == "capital"
    f3 = parse("해리포터의 저자는?")
    assert f3.subject == "해리포터" and f3.relation == "author"


def test_procedure_is_not_a_definition():
    f = parse("피자 맛있게 만드는 법")
    assert f.answer_type == "procedure" and f.subject == "피자"


def test_opinion_and_preference_are_conversational():
    assert parse("사랑이 뭐라고 생각해?").answer_type == "opinion"
    assert parse("인생에서 가장 중요한 게 뭐야?").answer_type == "opinion"
    assert parse("파이썬 좋아해?").answer_type == "preference"


def test_definition_and_entity():
    assert parse("양자역학이 뭐야?").answer_type == "definition"
    assert parse("양자역학이 뭐야?").subject == "양자역학"
    assert parse("손흥민이 누구야?").answer_type == "entity"


def test_bound_noun_never_becomes_subject():

    assert parse("인생에서 가장 중요한 게 뭐야?").subject not in ("게", "것", "건")


def test_single_char_subject_survives():
    f = parse("물의 화학식은?")
    assert f.subject == "물"  # 1-char subject not dropped (the old bug)


def test_wrong_referent_redteam_battery():
    """Subjects the spear/shield red-team found query_frame extracting WRONG.
    Fixed by (a) fronted-topic (no verb-stem subjects) + (b) concept-genitive
    discriminator. Nested-genitive stays a documented residual (needs the graph)."""
    from packages.graph_scale.query_frame import parse
    fixed = [
        ("세종대왕이 만든 것은?", "세종대왕"),
        ("상대성이론을 누가 만들었어?", "상대성이론"),
        ("토마토는 과일이야 채소야?", "토마토"),
        ("아인슈타인의 상대성이론은 무엇인가?", "상대성이론"),  # concept-genitive
        ("물의 화학식은?", "물"),                     # relation genitive still OK
        ("피자를 맛있게 만드는 법", "피자"),            # procedure still OK
    ]
    for q, want in fixed:
        assert parse(q).subject == want, (q, parse(q).subject)


def test_no_verb_stem_is_ever_a_subject():
    from packages.graph_scale.query_frame import parse, _VERBISH
    for q in ("세종대왕이 만든 것은?", "상대성이론을 누가 만들었어?", "물은 어떻게 끓어?"):
        subj = parse(q).subject
        assert not _VERBISH.search(subj), (q, subj)


def test_english_function_words_are_never_the_subject():
    """THE upstream origin of a whole failure family. Every other check in _ok_noun is Korean
    (question words, bound nouns, conjugated predicates) because this extractor was built for
    Korean; Kiwi tags English as SL and waved function words through as content nouns. Measured
    2026-07-17: parse("What does a polar bear look like?").subject == 'like', which fed
    semantic_frame → engage → "like is a kind of kind. like relates to unlike."
    Korean is head-final, so trailing-noun selection is right there and wrong here."""
    from packages.graph_scale.query_frame import _ok_noun, parse

    for w in ("like", "look", "better", "different", "kind", "thing"):
        assert not _ok_noun(w), w
    for w in ("polar", "bear", "gravity", "커피", "물리학"):
        assert _ok_noun(w), w

    # the whole noun phrase, not the bare head: 'Eiffel Tower' and 'Tower' are different things
    assert parse("What does a polar bear look like?").subject == "polar bear"
    assert parse("What does the Eiffel Tower look like?").subject == "Eiffel Tower"
    assert parse("What is a black hole?").subject == "black hole"
    assert parse("What is gravity?").subject == "gravity"
    # English genitives are head-FIRST: "the purpose of a firewall" is about the firewall
    assert parse("What is the purpose of a firewall?").subject == "firewall"
    assert parse("What's a firewall?").subject == "firewall"   # contraction stem must stop
    # Korean unaffected
    assert parse("커피가 뭐야").subject == "커피"
