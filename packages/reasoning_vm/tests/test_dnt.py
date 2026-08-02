# -*- coding: utf-8 -*-
"""DNT salience switch: route the input to CEN (factual/exam) / DMN (creative) / hybrid (emotional),
gate ALWAYS 1.00 (re-target grounding, never relax it)."""
from packages.reasoning_vm.dnt import salience, route


def test_mcq_routes_to_cen_exam():
    q = "다음 중 포유류는? ① 상어 ② 고래 ③ 참치 ④ 문어"
    assert salience(q) == "cen"
    r = route(q)
    assert r.mode == "cen" and r.handler == "answer_exam" and r.grounding == "world_facts"


def test_factual_question_is_cen():
    assert salience("프랑스의 수도는 어디야?") == "cen"
    assert route("프랑스의 수도는?").handler == "discriminate"


def test_creative_routes_to_dmn():
    for q in ["가을에 대한 시 하나 써줘", "짧은 이야기 하나 지어줘", "봄을 상상해서 노래 가사 써줘"]:
        assert salience(q) == "dmn", q
    r = route("가을에 대한 시를 지어줘")
    assert r.mode == "dmn" and r.handler == "felt_speech" and r.grounding == "internal_state+association"


def test_emotional_routes_to_hybrid():
    for q in ["오늘 너무 힘들어", "시험 망쳐서 속상해", "나 합격했어!"]:
        assert salience(q) == "hybrid", q
    assert route("너무 지쳤어").grounding == "user_state"


def test_subjective_routes_to_hybrid():
    assert salience("돈이 많으면 행복할까?") == "hybrid"
    assert salience("고양이랑 강아지 중 뭐가 더 나아?") == "hybrid"


def test_gate_is_always_one_no_relaxation():
    # the core doctrine correction: EVERY mode keeps the truth gate at 1.00 (re-target, not relax)
    for q in ["프랑스 수도는?", "가을 시 써줘", "너무 힘들어", "다음 중 옳은 것은? ① a ② b ③ c ④ d"]:
        assert route(q).gate == 1.0, q
