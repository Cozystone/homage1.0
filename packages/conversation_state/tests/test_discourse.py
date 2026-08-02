# -*- coding: utf-8 -*-
"""Deixis resolution: typed binding via graph, user-turn salience, honest no-ops."""
from __future__ import annotations

from packages.conversation_state import resolve_deixis, track_entities

CTX_JP = [{"role": "user", "content": "일본은 어떤 나라야?"},
          {"role": "assistant", "content": "일본은 동아시아의 섬나라입니다"}]


def test_typed_deixis_binds_graph_typed_entity():
    r = resolve_deixis("그럼 그 나라의 수도는?", CTX_JP)
    assert r["resolved"] == "그럼 일본의 수도는?"
    assert r["bindings"][0]["entity"] == "일본"


def test_user_turn_outranks_assistant_mention():
    ents = track_entities(CTX_JP)
    assert ents.index("일본") < ents.index("섬나라")


def test_person_name_ending_in_type_word_stays_eligible():
    # other test modules monkeypatch the shared bridge store to tmp stores —

    from packages.graph_scale import answer_bridge as ab

    ab._STORE = {"obj": None, "sig": None, "building": False, "built_at": 0.0}
    ctx = [{"role": "user", "content": "세종대왕에 대해 알려줘"},
           {"role": "assistant", "content": "세종대왕은 조선의 4대 왕입니다"}]
    r = resolve_deixis("그 사람이 만든 문자는?", ctx)
    assert "세종대왕" in r["resolved"]


def test_no_context_is_a_noop():
    r = resolve_deixis("그 나라의 수도는?", [])
    assert r["resolved"] == "그 나라의 수도는?"
    assert r["bindings"] == []


def test_no_deixis_is_a_noop():
    r = resolve_deixis("대한민국의 수도는?", CTX_JP)
    assert r["resolved"] == "대한민국의 수도는?"
