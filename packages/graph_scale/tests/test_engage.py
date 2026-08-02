# -*- coding: utf-8 -*-
"""No dead-end abstention: a hard-miss is engaged, never a bare 'I don't know'.
Honest by construction — nothing fabricated."""
from packages.graph_scale.engage import engage, _best_subject


class _FakeStore:
    def __init__(self, facts): self._f = facts
    def facts_about(self, t, limit=12): return self._f.get(t, [])


def test_engages_with_related_facts_never_dead_end():
    st = _FakeStore({"물": [("물", "defined_as", "무색무취의 액체"),
                            ("물", "is_a", "화합물")]})
    r = engage("물의 신비로운 힘은?", "ko", store=st)
    assert r is not None
    assert "모르" not in r["answer"] and "근거가 부족" not in r["answer"]
    assert "액체" in r["answer"]                       # offered a real fact
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False


def test_topic_before_about_phrase():
    assert _best_subject("서울특별시에 대해 자세히") == "서울특별시"
    assert _best_subject("커피란 뭐야") == "커피"


def test_unknown_still_engages_not_walls():
    st = _FakeStore({})
    r = engage("존재하지않는것xyz는?", "ko", store=st)
    assert r is not None and r["answer"]
    assert "모르겠" not in r["answer"]                  # forward cue, not a shrug
    assert r["engaged"] is True and r["grounded"] is False


def test_english_engagement():
    st = _FakeStore({"quark": [("quark", "is_a", "elementary particle")]})
    r = engage("tell me about the quark", "en", store=st)
    assert r is not None and "elementary particle" in r["answer"]
