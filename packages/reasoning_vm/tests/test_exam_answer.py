# -*- coding: utf-8 -*-
"""Exam mode never abstains, and its evidence rank is decided by the is_a taxonomy (the discrimination
lever the wiki harvest feeds). All tests use a SYNTHETIC in-memory graph — no world pack loaded."""
from packages.reasoning_vm.exam_answer import answer_exam, _evidence_score, _stem_terms



_G = {
    "고래": [("고래", "is_a", "고래목")],
    "고래목": [("고래목", "is_a", "포유류")],
    "상어": [("상어", "is_a", "연골어류")],
    "연골어류": [("연골어류", "is_a", "어류")],
    "참치": [("참치", "is_a", "어류")],
    "문어": [("문어", "is_a", "연체동물")],
}


def _fa(t):
    return _G.get(t, [])


def test_never_abstain_returns_a_pick_with_no_signal():
    r = answer_exam("전혀 모르는 질문", {"A": "가", "B": "나", "C": "다", "D": "라"}, lambda t: [])
    assert r["choice_key"] in {"A", "B", "C", "D"}         # always a pick
    assert r["mode"] == "guess" and r["confidence"] == 0.25


def test_transitive_isa_decides_categorization():

    stem = "다음 중 포유류인 것은?"
    choices = {"A": "상어", "B": "고래", "C": "참치", "D": "문어"}
    r = answer_exam(stem, choices, _fa)
    assert r["choice_key"] == "B", r
    assert r["mode"] in {"grounded", "inference"}          # decided by graph, not a blind guess


def test_isa_score_beats_zero_for_member_only():
    terms = _stem_terms("다음 중 포유류인 것은?")
    assert "포유류" in terms
    assert _evidence_score("고래", terms, _fa) >= 5.0       # transitive is_a hit
    assert _evidence_score("참치", terms, _fa) == 0.0


def test_negated_picks_the_odd_one_out():

    stem = "다음 중 어류가 아닌 것은?"
    choices = {"A": "상어", "B": "참치", "C": "고래"}
    r = answer_exam(stem, choices, _fa)
    assert r["choice_key"] == "C", r
