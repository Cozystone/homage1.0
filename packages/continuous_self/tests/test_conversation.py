# -*- coding: utf-8 -*-
"""Self-fused conversation routing — the self decides converse vs know."""

from __future__ import annotations

import packages.continuous_self.conversation as conv


def test_conversation_intents_route_to_converse():
    for q in ["안녕하세요", "너 기분 어때?", "파이썬 좋아해?",
              "인생에서 가장 중요한 게 뭐야?", "심심한데 재밌는 얘기 없어?",
              "이거 어떻게 해야 할까?"]:
        r = conv.perceive_route(q)
        assert r["mode"] == "converse", (q, r)


def test_knowledge_questions_route_to_know():
    for q in ["양자역학이 뭐야?", "일본의 수도는?", "커피 좋아하는 사람 많아?",
              "손흥민이 누구야?"]:
        r = conv.perceive_route(q)
        assert r["mode"] == "know", (q, r)


def test_frame_overrides_weak_router():

    # the query-frame grammar corrects them to conversation
    r = conv.perceive_route("파이썬 좋아해?")
    assert r["why"] == "query_frame" and r["intent"] == "preference"
    r2 = conv.perceive_route("인생에서 가장 중요한 게 뭐야?")
    assert r2["mode"] == "converse" and r2["intent"] == "opinion"


def test_converse_generates_from_state_never_fabricates():
    r = conv.converse("너 기분 어때?", "feeling")
    assert r and "기분" in r["answer"]
    g = r["reasoning_certificate"]["guarantees"]
    assert g["fabricated_facts"] is False and g["generated_from_self_state"] is True


def test_greeting_and_social_reply():
    assert conv.converse("안녕하세요", "greeting")["answer"].startswith("안녕")
    assert conv.converse("고마워", "social") is not None
