# -*- coding: utf-8 -*-
"""C4 learned realizer: the is LEARNED (induced discourse grammar) + FUSES , not templated.
Grounding is a hard gate; facts are never dropped or invented."""
from packages.base_brain.learned_realizer import (
    grounding_ok,
    mine_grammar,
    realize_fused,
)

_PROSE = [
    "애플 주식회사는 실리콘 밸리의 쿠퍼티노에 본사를 둔 미국의 다국적 기업이자 기술 회사이다.",
    "이 회사는 소비자 가전, 소프트웨어, 서비스로 가장 잘 알려져 있다.",
    "엔비디아는 그래픽 처리 장치를 설계하는 기업이며, 인공지능 분야에서 선도적이다.",
    "그는 물리학자이자 수학자였으며, 여러 이론을 정립하였다.",
]


def test_grammar_is_induced_from_prose_not_hand_listed():
    g = mine_grammar(_PROSE)
    assert g["n"] == 4

    assert g["noun_connectives"]
    assert set(g["noun_connectives"]) <= {"이며", "이자", "이고"}
    assert g["fusion_rate"] > 0                      # the prose fuses clauses → learned > 0


def test_fusion_makes_one_sentence_and_kills_enumeration():
    g = mine_grammar(_PROSE)
    clauses = ["미국의 다국적 기술 회사", "소비자 가전으로 잘 알려져 있다", "1976년에 설립되었다"]
    out = realize_fused("애플", clauses, g=g)
    assert out.count(".") == 1                       # ONE fused sentence, not 3 enumerated
    assert "먼저" not in out and "또한" not in out and "끝으로" not in out
    assert out.startswith("애플은")                   # topic stated once, then fused


def test_grounding_gate_every_fact_survives():
    g = mine_grammar(_PROSE)
    clauses = ["카페인이 들어 있는 음료", "각성 효과가 있다"]
    out = realize_fused("커피", clauses, g=g)
    assert grounding_ok(out, clauses)                # both facts present in the fused output
    assert "카페인" in out and "각성" in out


def test_grounding_gate_rejects_a_dropped_fact():
    # a fabricated 'output' that lost a grounded clause must FAIL the gate (the hard gate that lets
    # grounded_generation fall back to templates rather than emit an ungrounded fusion).
    clauses = ["카페인이 들어 있는 음료", "각성 효과가 있다"]
    assert not grounding_ok("커피는 카페인이 들어 있는 음료예요.", clauses)


def test_noun_connective_is_grammatical_not_mangled():
    g = {"noun_connectives": {"이며": 1}, "fusion_rate": 1.0, "backref_rate": 0.0}
    out = realize_fused("회사", ["미국의 기술 기업", "여러 제품을 만든다"], g=g)
    assert "기업이며" in out                          # noun + copula-connective, correct allomorph


def test_single_fact_still_realizes():
    out = realize_fused("커피", ["카페인이 들어 있는 음료"], g=mine_grammar(_PROSE))
    assert out and out.startswith("커피는") and out.endswith(".")


def test_kiwi_conjugates_present_tense_connective_correctly():
    """The clause connective must be morphologically correct, not a surface ''-strip: the fused
 '' becomes '' (Kiwi, the single-authority morpheme engine), never the broken ''.
 Skips only if Kiwi is unavailable in the environment."""
    from packages.base_brain.learned_realizer import _kiwi, _to_connective
    if _kiwi() is None:
        return
    assert _to_connective("높이가 8848미터에 이른다", connective="고") == "높이가 8848미터에 이르고"
    assert _to_connective("여러 제품을 만든다", connective="고") == "여러 제품을 만들고"
    assert _to_connective("과학을 발전시켰다", connective="고") == "과학을 발전시켰고"        # past kept
