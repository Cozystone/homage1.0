# -*- coding: utf-8 -*-
"""Recursive realizer: novel grammatical sentences, provably grounded."""
from packages.grounded_composer.recursive_realizer import realize

FACTS = [("서울특별시", "is_a", "도시"), ("서울특별시", "located_in", "대한민국"),
         ("서울특별시", "인구", "9,668,465"), ("서울특별시", "설립", "1395년")]


def test_composes_novel_embedded_sentence():
    r = realize("서울특별시", FACTS, max_modifiers=2)
    assert r is not None
    assert "대한민국에 위치한" in r.text and "도시" in r.text
    assert r.text.endswith("습니다.") or r.text.endswith("입니다.")


def test_every_content_token_from_facts():
    r = realize("서울특별시", FACTS, max_modifiers=2)
    objs = {o for _s, _p, o in r.facts_used}
    for o in objs:
        assert o in r.text            # verbatim grounding
    assert set(r.facts_used) <= set(FACTS)


def test_parameter_variation_yields_distinct_sentences():
    a = realize("서울특별시", FACTS, max_modifiers=1).text
    b = realize("서울특별시", FACTS, max_modifiers=2).text
    assert a != b                     # finite means, many sentences


def test_no_head_or_single_fact_returns_none():
    assert realize("커피", [("커피", "defined_as", "음료이다")]) is None
    assert realize("x", [("x", "인구", "5")]) is None


def test_head_must_speak_korean():
    r = realize("일본", [("일본", "is_a", "Japan"), ("일본", "인구", "1억")])
    assert r is None                  # falls back to existing paths
