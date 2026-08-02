# -*- coding: utf-8 -*-
"""C1 statement entailment: decompose a choice-STATEMENT into a claim and verify it against the
graph — the un-hallucinatable conceptual-MCQ move (pick the graph-supported statement / odd-one-out,
abstain otherwise)."""
from packages.reasoning_vm.statement_entailment import (
    extract_claim, verify_statement, discriminate_conceptual)

# tiny world: is_a taxonomy + a capital
_KG = {
    "고래": [("고래", "is_a", "포유류")],
    "개": [("개", "is_a", "포유류")],
    "소": [("소", "is_a", "포유류")],
    "상어": [("상어", "is_a", "어류")],
    "대한민국": [("대한민국", "capital", "서울"), ("대한민국", "is_a", "국가")],
    "포유류": [("포유류", "is_a", "동물")],
}


def _fa(subject):
    return _KG.get(subject, [])


# ── claim extraction (surface parse only) ─────────────────────────────────────────────────────
def test_extract_returns_none_without_two_args():
    assert extract_claim("좋다") is None



def test_verb_noun_without_case_markers_stays_unverifiable():

    # yield an unmatched claim, so it stays UNVERIFIED against a real graph (never a false positive).
    assert verify_statement("발견은 중요하다", _fa) == "UNVERIFIED"


# ── verification against the graph ────────────────────────────────────────────────────────────
def test_verify_unverified_when_graph_refutes():
    assert verify_statement("고래는 어류이다", _fa) == "UNVERIFIED"


def test_verify_unverified_when_uncovered():
    assert verify_statement("힉스 입자는 소립자이다", _fa) == "UNVERIFIED"


def test_transitive_does_not_over_support():

    assert verify_statement("상어는 포유류이다", _fa) == "UNVERIFIED"


# ── conceptual MCQ: pick the single supported statement / the odd-one-out ──────────────────────
def test_conceptual_abstains_when_none_supported():
    v = discriminate_conceptual(
        "다음 중 옳은 것은?",
        {"A": "힉스 입자는 보손이다", "B": "쿼크는 렙톤이다", "C": "중성자는 렙톤이다", "D": "전자는 쿼크이다"}, _fa)
    assert v.status == "ABSTAIN"                               # graph covers none → honest silence


def test_conceptual_abstains_when_multiple_supported():
    v = discriminate_conceptual(
        "다음 중 옳은 것은?",
        {"A": "고래는 포유류이다", "B": "개는 포유류이다", "C": "상어는 어류이다", "D": "고래는 광물이다"}, _fa)
    assert v.status == "ABSTAIN"                               # 3 supported → can't isolate one
