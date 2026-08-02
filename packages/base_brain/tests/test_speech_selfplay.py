# -*- coding: utf-8 -*-
from packages.base_brain.speech_selfplay import best_of, critique

_FACTS = ["커피는 카페인을 함유한 음료이다", "하루 권장 카페인은 400mg이다"]


def test_faithfulness_is_a_hard_gate():
    fabricated = critique("커피는 우주에서 온 외계 물질이에요.", _FACTS, "커피?")
    assert fabricated["faithful"] is False
    assert fabricated["total"] == 0.0     # unfaithful → zero, however fluent


def test_run_on_and_repetition_are_penalised():
    clean = critique("커피는 카페인을 함유한 음료예요. 하루 권장 카페인은 400mg이에요.", _FACTS)
    messy = critique("커피는 카페인을 함유한 음료이다 또한 하루 권장 카페인은 400mg이다 또한 그리고 "
                     "이것은 매우 길고 장황하게 계속 이어지는 부자연스러운 문장입니다 그리고", _FACTS)
    assert clean["fluency"] > messy["fluency"]
    assert clean["total"] > messy["total"]


def test_best_of_picks_the_fluent_faithful_phrasing():
    a = "커피는 카페인을 함유한 음료이다 또한 하루 권장 카페인은 400mg이다 또한 그리고 계속 길게"
    b = "커피는 카페인을 함유한 음료예요. 하루 권장 카페인은 400mg이에요."
    c = "커피는 우주에서 온 외계 물질이에요."
    r = best_of([a, b, c], _FACTS, "커피 카페인?")
    assert r["best"] == b
    assert r["best_score"]["faithful"] is True
