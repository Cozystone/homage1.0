# -*- coding: utf-8 -*-
"""Subjective context: the SAME dwell reads differently by what was said."""
from packages.graph_scale.subjective_context import valence_from_utterance, interpret


def test_valence_reads_admiration_skepticism_and_neutral():
    assert valence_from_utterance("와 이건 진짜 대박인데")["stance"] == "admiring"
    assert valence_from_utterance("이야 이건 진짜 쉽지 않은데.. 되겠나 이거")["stance"] == "skeptical"
    assert valence_from_utterance("음 그렇구나")["stance"] == "neutral"
    assert valence_from_utterance("별로 안 예쁘네")["stance"] == "negative"


def test_same_dwell_opposite_reads():
    admired = interpret(20.0, "와 이건 대박인데")
    doubtful = interpret(20.0, "되겠나 이거 쉽지 않은데")
    assert admired["read"] == "admired" and admired["phrase"] == "감탄하며 보셨던"
    assert doubtful["read"] == "engaged_but_doubtful" and "긴가민가" in doubtful["phrase"]
    # a glance (short dwell) is neither, regardless of words
    assert interpret(1.5, "와 대박")["read"] == "passing"
