# -*- coding: utf-8 -*-
"""User deep model — derivation is pure and evidence-backed (no store I/O)."""

from __future__ import annotations

from datetime import date, timedelta

from packages.user_model import derive_user_model, summary_facts, user_context_line


def _ev(pred: str, obj: str, days_ago: int, subject: str = "사용자") -> dict:
    at = (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {"at": at, "subject": subject, "predicate": pred, "object": obj,
            "note": "", "source": "test"}


def test_possessions_age_and_evidence():
    events = [_ev("구매", "물병", 1100), _ev("구매", "노트북", 200)]
    m = derive_user_model(events=events, brain_facts=[])
    objs = {p["object"]: p for p in m["possessions"]}
    assert objs["물병"]["age_days"] == 1100
    assert objs["물병"]["evidence_count"] == 1
    assert objs["노트북"]["age_days"] == 200
    # oldest first — repurchase candidates surface first
    assert m["possessions"][0]["object"] == "물병"


def test_habit_periodicity_needs_three_events():
    two = [_ev("방문", "카페", 10), _ev("방문", "카페", 5)]
    m = derive_user_model(events=two, brain_facts=[])
    assert m["habits"] == []  # 2 events never claim a rhythm

    three = two + [_ev("방문", "카페", 0)]
    m = derive_user_model(events=three, brain_facts=[])
    assert len(m["habits"]) == 1
    h = m["habits"][0]
    assert h["count"] == 3
    assert h["median_interval_days"] == 5  # measured, not invented


def test_preferences_merge_both_sources():
    events = [_ev("선호", "아메리카노", 3), _ev("싫어함", "민트초코", 2)]
    facts = [{"kind": "preference", "subject": "음악", "value": "재즈", "confidence": 0.75}]
    m = derive_user_model(events=events, brain_facts=facts)
    polarities = {p["value"]: p["polarity"] for p in m["preferences"]}
    assert polarities["아메리카노"] == "positive"
    assert polarities["민트초코"] == "negative"
    assert any(p["source"] == "local_brain" for p in m["preferences"])


def test_summary_and_context_line_are_grounded():
    events = [_ev("구매", "물병", 1100), _ev("방문", "카페", 10),
              _ev("방문", "카페", 5), _ev("방문", "카페", 0)]
    m = derive_user_model(events=events, brain_facts=[])
    sents = summary_facts(m)
    assert any("물병" in s and "근거" in s for s in sents)
    line = user_context_line(m)
    assert line and "물병" in line and "카페" in line


def test_empty_stores_stay_silent():
    m = derive_user_model(events=[], brain_facts=[])
    assert m["possessions"] == [] and m["habits"] == [] and m["preferences"] == []
    assert summary_facts(m) == []
    assert user_context_line(m) is None  # silence over invention
