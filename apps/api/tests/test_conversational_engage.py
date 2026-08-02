# -*- coding: utf-8 -*-
"""Omni-engage: non-factual questions get warm sensible answers, facts stay factual.

The AI directive done honestly — answer everything sensibly, never
fabricate. Opinion/preference/advice/small-talk engage; factual lookups keep
their grounded answers; hallucination stays 0 (verified by the hard battery).
"""
from __future__ import annotations

import re

from app.routers.dual_brain import _conversational_engage_answer


def _kind(q):
    r = _conversational_engage_answer(q, "ko")
    return r["answer_kind"] if r else None


def test_preference_addressed_to_atanor_engages():
    r = _conversational_engage_answer("파이썬 좋아해?", "ko")
    assert r and r["answer_kind"] == "conversational_engage"
    assert "지어내" in r["answer"]  # honest about not fabricating


def test_preference_about_others_is_NOT_stolen():

    assert _conversational_engage_answer("커피 좋아하는 사람 많아?", "ko") is None


def test_opinion_value_question_engages():
    r = _conversational_engage_answer("인생에서 가장 중요한 게 뭐야?", "ko")
    assert r and r["answer_kind"] == "conversational_engage"
    assert "정직" in r["answer"] or "진짜" in r["answer"]


def test_smalltalk_engages_warmly():
    r = _conversational_engage_answer("심심한데 재밌는 얘기 없어?", "ko")
    assert r and "심심" in r["answer"]


def test_advice_engages():
    assert _kind("이거 어떻게 해야 할까?") == "conversational_engage"


def test_definition_questions_are_NOT_stolen():
    # genuine factual/definition questions must fall through (return None)
    for q in ("양자역학이 뭐야?", "서울이란?", "고양이가 뭐야?", "커피는 뭐야?"):
        assert _conversational_engage_answer(q, "ko") is None, q


def test_never_fabricates_flag():
    r = _conversational_engage_answer("너 어떻게 생각해?", "ko")
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False
    assert r["reasoning_certificate"]["guarantees"]["external_llm"] is False


def test_english_falls_through():
    assert _conversational_engage_answer("do you like python?", "en") is None
