# -*- coding: utf-8 -*-
"""Register-balanced diet — the fix for the measured bottleneck (corpus is 52% Wikipedia, 2% dialogue,
so scaling it doesn't raise speaking quality). Balance by REGISTER so /// come evenly."""
from __future__ import annotations

import random

from packages.autonomy_kernel.register_diet import (
    REGISTERS,
    balanced_draw,
    classify_register,
    register_mix,
    under_registers,
)


def test_classifier_separates_the_four_registers_on_real_examples():
    # real lines drawn from the actual corpus + representative dialogue/english
    assert classify_register("호세 고메스 1944년 2014년 는 스페인의 자전거 경기 선수이다") == "knowledge"
    assert classify_register("안심뉴타운은 대구광역시 동구 안심동 일대에 개발 중인 뉴타운이다") == "knowledge"
    assert classify_register("커피 원두 뭐가 좋아? 산미 있는 거 추천해줘") == "dialogue"
    assert classify_register("아 그거 진짜 웃기지 않냐 ㅋㅋ") == "dialogue"
    assert classify_register("The mitochondria is the powerhouse of the cell") == "english"
    # a general statement with no date / stub / dialogue marker → commonsense
    assert classify_register("물은 낮은 곳으로 흐른다") == "commonsense"


def test_register_mix_reports_the_distribution():
    lines = ["1999년에 태어난 선수이다", "커피 좋아?", "Hello there friend", "물은 아래로 흐른다"]
    mix = register_mix(lines)
    assert mix["total"] == 4
    assert mix["counts"]["knowledge"] == 1 and mix["counts"]["dialogue"] == 1
    assert mix["counts"]["english"] == 1 and mix["counts"]["commonsense"] == 1


def test_balanced_draw_evens_out_a_wikipedia_heavy_corpus():
    # 90 knowledge, 6 dialogue, 3 english, 3 commonsense — a Wikipedia-dominated corpus like ours
    lines = ([f"{1900+i}년에 지어진 건물이다" for i in range(90)]
             + [f"이거 {i} 어때 ㅋㅋ" for i in range(6)]
             + [f"This is english line {i} here" for i in range(3)]
             + [f"사람은 누구나 실수를 한다 {i}" for i in range(3)])
    rng = random.Random(0)
    natural = register_mix(lines)["fractions"]
    assert natural["knowledge"] > 0.8                      # the corpus is knowledge-dominated
    drawn = balanced_draw(lines, 16, rng)
    dm = register_mix(drawn)["counts"]
    # every register that HAS material is represented; knowledge no longer dominates the sample
    assert dm["dialogue"] >= 4 and dm["english"] >= 3 and dm["commonsense"] >= 3
    assert dm["knowledge"] <= 6                            # capped, not 80%+


def test_under_registers_flags_the_gaps_to_steer_mining():
    lines = ([f"{1900+i}년 선수이다" for i in range(80)]
             + ["커피 좋아?" for _ in range(20)])          # knowledge-heavy, some dialogue, no english
    gaps = under_registers(lines, floor=0.20)
    assert "english" in gaps and "commonsense" in gaps     # both starved → steer sourcing there
    assert "knowledge" not in gaps                          # knowledge is over-represented, not a gap
