# -*- coding: utf-8 -*-
"""Privacy-as-architecture is the property under test: raw titles never survive,
sensitive contexts are redacted before distillation, and interests decay with recency."""
from __future__ import annotations

from packages.perception_stream import ContextLedger, distill_activity


def test_raw_title_is_discarded_only_concepts_kept():
    ev = distill_activity("firefox", "광합성 - 위키백과 — Mozilla Firefox", "2026-07-06T10:00:00")
    d = ev.to_dict()
    assert "광합성" in ev.concepts
    assert "Mozilla Firefox" not in str(d) and "위키백과" != d.get("title", "")
    assert d["raw_discarded"] is True and d["left_device"] is False


def test_browser_chrome_is_stripped():
    ev = distill_activity("chromium", "쿠버네티스 입문 - Google Chrome", "2026-07-06T10:00:00")
    assert "쿠버네티스" in ev.concepts
    assert not any("chrome" in c.lower() for c in ev.concepts)


def test_sensitive_context_is_redacted_before_distillation():
    ev = distill_activity("firefox", "은행 로그인 - 비밀번호 입력", "2026-07-06T10:00:00")
    assert ev.redacted is True and ev.concepts == []
    ev2 = distill_activity("chromium", "Private Browsing", "2026-07-06T10:00:00")
    assert ev2.redacted is True


def test_ledger_interests_are_recency_weighted(tmp_path):
    led = ContextLedger(tmp_path / "ctx.jsonl")
    # old topic, then a run of a new topic
    led.record(distill_activity("firefox", "하스켈 튜토리얼", "t0"))
    for _ in range(20):
        led.record(distill_activity("firefox", "쿠버네티스 운영", "t1"))
    interests = dict(led.interests())
    assert interests.get("쿠버네티스", 0) > interests.get("하스켈", 0)


def test_ledger_stats_prove_no_raw_stored(tmp_path):
    led = ContextLedger(tmp_path / "ctx.jsonl")
    led.record(distill_activity("firefox", "그래프 이론 - Firefox", "t"))
    led.record(distill_activity("firefox", "은행 비밀번호", "t"))  # redacted
    s = led.stats()
    assert s["events"] == 2 and s["redacted"] == 1
    assert s["guarantees"]["raw_content_stored"] is False
    assert s["guarantees"]["left_device"] is False


def test_ledger_is_bounded(tmp_path):
    led = ContextLedger(tmp_path / "ctx.jsonl", max_events=10)
    for i in range(25):
        led.record(distill_activity("firefox", f"주제{i}", "t"))
    assert len(led.recent(limit=100)) <= 10
