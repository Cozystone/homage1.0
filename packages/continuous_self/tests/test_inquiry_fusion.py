# -*- coding: utf-8 -*-
"""Self-awareness -> answer-depth fusion: engaged topics get answered deeper."""

from __future__ import annotations

from packages.continuous_self.inquiry_fusion import (
    depth_bias, extra_relation_budget, preoccupation, engagement_note,
)


def _state(**kw):
    base = {"self_question": "", "self_question_open": False, "curiosity": 0.5,
            "last_inquiry_topic": "", "recent_insights": []}
    base.update(kw)
    return base


def test_engaged_subject_biases_higher_than_unrelated():
    st = _state(self_question="나는 왜 의식이 있다고 말할 수 있을까", self_question_open=True,
                curiosity=0.8, last_inquiry_topic="의식")
    assert depth_bias("의식", st) > 0.5
    assert depth_bias("피자", st) == 0.0  # unrelated -> no change


def test_no_preoccupation_means_no_bias():
    st = _state()  # the self isn't pondering anything
    assert preoccupation(st) == set()
    assert depth_bias("의식", st) == 0.0


def test_extra_budget_grows_with_bias_and_is_bounded():
    assert extra_relation_budget(0.0) == 3
    assert extra_relation_budget(1.0) == 7      # base 3 + up to 4
    assert extra_relation_budget(0.5) == 5
    # never unbounded
    assert extra_relation_budget(9.9) <= 7


def test_open_question_activates_more_than_closed():
    open_st = _state(self_question="시간이란 무엇인가", self_question_open=True, last_inquiry_topic="시간")
    closed_st = _state(self_question="시간이란 무엇인가", self_question_open=False, last_inquiry_topic="시간")
    assert depth_bias("시간", open_st) > depth_bias("시간", closed_st)


def test_engagement_note_only_when_engaged():
    assert engagement_note("의식", 0.0) == ""
    assert "의식" in engagement_note("의식", 0.8)
