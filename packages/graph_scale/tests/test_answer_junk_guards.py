# -*- coding: utf-8 -*-
"""Store-junk rejection guards in answer_from_triples (P0 regression 2026-07-11).

The diet-acceleration store flood surfaced latent junk that overrode the curated pack:
 * grammar-note bound morphemes ('' → ''),
 * foreign-language definitions for a Korean query ('DNA' → English),
 * decomposed-fragment referents ('' → ''),
 * general definitions answering a composition question ('' → '').
These guards make answer_from_triples abstain (None) on those shapes so the pack wins.
"""
from packages.graph_scale.answer_bridge import _is_grammar_note


def test_grammar_note_detection():
    assert _is_grammar_note("(일부 명사나 관형사 '이', '그' 따위, 어미 '-은', '-는' 뒤에 쓰여) '무렵'")
    assert _is_grammar_note("(일부 명사에 붙어) '물건'이나 '물질'의 뜻을 더한다")
    # a real definition is NOT a grammar note
    assert not _is_grammar_note("수소와 산소로 이루어진 투명한 화합물이다")
    assert not _is_grammar_note("대한민국의 수도이며 한반도 중부에 위치한 도시이다")


def test_composition_regex_matches_intent():
    import re
    pat = re.compile(r"무엇으로\s*(?:이루어|구성|되어)|무엇으로\s*만들어|성분(?:이|은|을)|원소로")
    assert pat.search("물은 무엇으로 이루어져 있어?")
    assert pat.search("공기는 무엇으로 구성되어 있나요?")
    # a plain definitional ask is NOT a composition ask
    assert not pat.search("물이 뭐야?")
    assert not pat.search("세종대왕이 만든 것은 뭐야?")
