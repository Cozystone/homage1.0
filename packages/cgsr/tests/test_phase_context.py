"""Holographic phase-context: generation conditions on the WHOLE context, not just the last token."""
from __future__ import annotations

from cgsr.phase_context import PhaseField, Superposition

CORPUS = [
    "고양이 는 동물 이다", "고양이 가 야옹 하고 운다", "강아지 는 동물 이다",
    "강아지 가 멍멍 하고 짖는다", "토끼 는 동물 이고 귀엽다",
    "컴퓨터 는 기계 이다", "컴퓨터 가 계산 을 한다", "로봇 은 기계 이고 작동 한다",
    "서버 는 계산 을 처리 한다", "기계 는 전기 로 작동 한다",
]


def _sup(field, tokens):
    s = Superposition(field)
    for t in tokens:
        s.add(t)
    return s


def test_context_superposition_flips_ranking_by_topic():
    # The core upgrade: the SAME candidate pair ranks differently depending on the whole

    field = PhaseField(CORPUS)
    animal = _sup(field, ["고양이", "는"])
    assert animal.interference("동물") > animal.interference("기계")
    machine = _sup(field, ["컴퓨터", "는"])
    assert machine.interference("기계") > machine.interference("동물")


def test_off_topic_candidate_interferes_destructively():
    field = PhaseField(CORPUS)
    animal = _sup(field, ["고양이", "는", "동물"])
    # a machine-topic token should not out-score an animal-topic continuation here
    assert animal.interference("동물") > animal.interference("전기")


def test_empty_context_is_neutral():
    field = PhaseField(CORPUS)
    assert Superposition(field).interference("동물") == 0.0  # no context → no opinion


def test_unknown_token_is_neutral():
    field = PhaseField(CORPUS)
    s = _sup(field, ["고양이"])
    assert s.interference("존재하지않는토큰") == 0.0


def test_deterministic():
    a = PhaseField(CORPUS).phasor("동물")
    b = PhaseField(CORPUS).phasor("동물")
    assert (a == b).all()
