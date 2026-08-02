# -*- coding: utf-8 -*-
"""Open-book MCQ: retrieve the entity's real passage, pick the option it supports. Synthetic passages
(no harvested file) so the logic is tested in isolation."""
from packages.reasoning_vm.openbook import answer_openbook, retrieve

_P = {
    "광합성": "광합성은 빛 에너지를 이용하여 이산화탄소와 물로부터 포도당과 산소를 만드는 대사 과정이다",
    "삼투압": "삼투압은 반투막을 경계로 농도가 낮은 쪽에서 높은 쪽으로 용매가 이동하는 현상에서 나타나는 압력이다",
}


def test_retrieve_by_title_with_josa():
    got = retrieve("광합성에 필요한 것은?", _P)
    assert got is not None and got[0] == "광합성"


def test_single_char_answer_supported():

    r = answer_openbook("광합성에 필요한 것은?", {"A": "빛", "B": "소리", "C": "바람", "D": "철"}, _P)
    assert r and r["choice_key"] == "A" and r["mode"] == "openbook"


def test_multitoken_answer_supported():
    r = answer_openbook("광합성의 산물은?", {"A": "포도당", "B": "단백질", "C": "지방", "D": "핵산"}, _P)
    assert r and r["choice_key"] == "A"


def test_negated_picks_unsupported_option():
    r = answer_openbook("광합성과 관련 없는 것은?",
                        {"A": "빛", "B": "이산화탄소", "C": "화폐", "D": "물"}, _P)
    assert r and r["choice_key"] == "C"


def test_no_passage_returns_none_not_a_guess():
    # nothing to retrieve → None, so the caller's cascade owns the never-abstain decision.
    assert answer_openbook("블랙홀의 성질은?", {"A": "가", "B": "나", "C": "다", "D": "라"}, _P) is None


def test_indistinct_passage_returns_none():
    # passage supports every option equally → no discriminating signal → None (honest, not a guess).
    P = {"물": "물은 수소와 산소로 이루어진 화합물이다"}
    r = answer_openbook("물에 대한 설명은?",
                        {"A": "수소", "B": "산소", "C": "화합물", "D": "이루어진"}, P)
    assert r is None


# ── Pattern A: options are ENTITIES, each with its own passage ────────────────────────────────────
_PA = {
    "고래": "고래는 바다에 사는 포유류이다",
    "상어": "상어는 연골어류에 속하는 어류이다",
    "참치": "참치는 고등어과의 바닷물고기로 어류이다",
    "문어": "문어는 연체동물이다",
}


def test_pattern_a_entity_options():
    # stem has no retrievable entity; the ANSWER is decided by each option's own passage.
    r = answer_openbook("다음 중 포유류인 것은?", {"A": "상어", "B": "고래", "C": "참치", "D": "문어"}, _PA)
    assert r and r["choice_key"] == "B"


def test_pattern_a_negated():
    r = answer_openbook("다음 중 어류가 아닌 것은?", {"A": "상어", "B": "참치", "C": "고래"}, _PA)
    assert r and r["choice_key"] == "C"
