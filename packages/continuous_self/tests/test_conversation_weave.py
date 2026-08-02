# -*- coding: utf-8 -*-
"""Conversation weave — the session model for an always-on voice presence: one continuous stream,
threads by resonance (not time), emergent episodes. Proves the owner's bias ("=") is dissolved:
an interleaved topic REJOINS its thread across an episode boundary."""
from __future__ import annotations

from packages.continuous_self.conversation_weave import (
    by_episode,
    by_thread,
    ingest,
    load_state,
    new_state,
    resolve_deixis,
    save_state,
    set_concept_expander,
    warm_thread,
)


def test_same_topic_joins_one_thread_new_topic_starts_another():
    st = new_state()
    a1 = ingest(st, "커피 좋아", ts=1000.0)
    a2 = ingest(st, "커피 원두 사고싶어", ts=1005.0)
    b1 = ingest(st, "날씨 정말 춥다", ts=1010.0)
    assert a2["thread_id"] == a1["thread_id"]          # coffee → coffee: same thread
    assert a2["new_thread"] is False
    assert b1["thread_id"] != a1["thread_id"]          # weather: a new thread
    assert b1["new_thread"] is True


def test_interleaved_topic_rejoins_its_thread_across_an_episode():
    # THE proof: coffee … weather … coffee — the third utterance rejoins the COFFEE thread (resonance,
    # not recency), even though the weather turn opened a new episode in between. Threads > sessions.
    st = new_state()
    a1 = ingest(st, "커피 좋아", ts=1000.0)
    _b = ingest(st, "날씨 정말 춥다", ts=1005.0)
    a3 = ingest(st, "커피 가격 알려줘", ts=1010.0)
    assert a3["thread_id"] == a1["thread_id"]          # rejoined the coffee thread
    assert a3["new_thread"] is False
    assert a3["episode_id"] != a1["episode_id"]        # but it is a DIFFERENT episode (topic moved & back)


def test_long_silence_opens_a_new_episode_same_thread():
    st = new_state()
    a1 = ingest(st, "커피 원두 좋아", ts=1000.0)
    # same topic, but 40 minutes later — a natural episode boundary despite the shared thread
    a2 = ingest(st, "커피 원두 더 살까", ts=1000.0 + 2400.0)
    assert a2["thread_id"] == a1["thread_id"]          # still the coffee thread
    assert a2["new_episode"] is True                   # yet a new episode (the relationship went quiet)


def test_topic_shift_opens_a_new_episode():
    st = new_state()
    e1 = ingest(st, "커피 원두 좋아", ts=2000.0)
    e2 = ingest(st, "상대성이론 시간 팽창 설명", ts=2005.0)   # unrelated subject, seconds later
    assert e2["new_episode"] is True and e2["episode_id"] != e1["episode_id"]


def test_deixis_resolves_to_the_warm_threads_focus():
    st = new_state()
    ingest(st, "커피 좋아", ts=3000.0)
    ingest(st, "커피 원두 사고싶어", ts=3005.0)
    ingest(st, "커피 가격 궁금해", ts=3010.0)

    assert resolve_deixis(st, "이거", now=3011.0) == "커피"
    assert resolve_deixis(st, "그거 어때", now=3011.0) == "커피"
    # a non-deictic term names its own referent, unchanged
    assert resolve_deixis(st, "날씨", now=3011.0) == "날씨"
    assert warm_thread(st, now=3011.0)["count"] == 3


def test_lenses_are_consistent_views_of_one_weave():
    st = new_state()
    for i, msg in enumerate(["커피 좋아", "커피 원두 사", "날씨 춥다", "커피 맛 최고"]):
        ingest(st, msg, ts=4000.0 + i * 5)
    threads = by_thread(st)
    episodes = by_episode(st)
    # every utterance belongs to exactly one episode across the lens
    all_in_episodes = [uid for ep in episodes for uid in ep["utterance_ids"]]
    assert sorted(all_in_episodes) == [u["id"] for u in st["utterances"]]
    # the coffee thread gathers its three coffee turns even though a weather turn split them
    coffee = max(threads, key=lambda t: t["count"])
    assert coffee["count"] == 3


def test_continuation_rides_the_warm_thread_not_a_new_one():

    # (and not open a new episode), so the deictic reference stays resolvable.
    st = new_state()
    a1 = ingest(st, "커피 원두 좋아", ts=6000.0)
    ingest(st, "커피 산미 궁금해", ts=6005.0)
    cont = ingest(st, "이거 계속하자", ts=6010.0)
    assert cont["thread_id"] == a1["thread_id"]        # rode the coffee thread
    assert cont["new_thread"] is False
    assert cont["new_episode"] is False                # no topic shift → no new episode
    assert resolve_deixis(st, "이거", now=6011.0) == "커피"


def test_semantic_expander_merges_a_subtopic_into_its_thread():

    # subtopic joins the coffee thread instead of fragmenting. (Reset the hook after.)
    try:
        set_concept_expander(lambda cs: {"커피"} if "아메리카노" in cs else set())
        st = new_state()
        a1 = ingest(st, "커피 좋아", ts=7000.0)
        sub = ingest(st, "아메리카노가 최고야", ts=7005.0)
        assert sub["thread_id"] == a1["thread_id"]
        assert sub["new_thread"] is False
    finally:
        set_concept_expander(None)


def test_persistence_round_trip(tmp_path):
    st = new_state()
    ingest(st, "커피 좋아", ts=5000.0)
    ingest(st, "커피 원두 사고싶어", ts=5005.0)
    p = tmp_path / "weave.json"
    save_state(p, st)
    back = load_state(p)
    assert len(back["utterances"]) == 2
    assert resolve_deixis(back, "이거", now=5006.0) == "커피"   # survives a reload
