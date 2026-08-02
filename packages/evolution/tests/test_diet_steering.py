# -*- coding: utf-8 -*-
"""Diet steering — the arena's weakness aims the mining, safely and self-fading.

Guarantees:
 1. only seeds scored BELOW the floor become targets (strong lanes are not chased);
 2. a target's pull DECAYS with time (a fed topic stops being chased on its own);
 3. next_target skips recently-visited topics and yields None when nothing is pressing
 (a soft steer — the graph frontier still leads);
 4. topic extraction strips so the mined search term is the bare topic.
"""
from __future__ import annotations

import time

from packages.evolution import diet_steering as ds


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "TARGETS_PATH", tmp_path / "diet_targets.jsonl")


def test_only_weak_seeds_become_targets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    n = ds.record_weakness([("바다는", 0.2), ("지식이", 0.9), ("고요가", 0.4)], floor=0.6)
    assert n == 2
    topics = {t for t, _p in ds._live_targets()}
    assert "바다" in topics and "고요" in topics and "지식" not in topics


def test_topic_extraction_strips_josa():
    assert ds._topic_of("바다는 잔잔하다") == "바다"
    assert ds._topic_of("지식이") == "지식"


def test_pull_decays_over_time(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    old = time.time() - 24 * 3600  # a full day ago (4 half-lives)
    (tmp_path / "diet_targets.jsonl").write_text(
        '{"topic": "바다", "strength": 0.4, "ts": %f}\n' % old, encoding="utf-8")
    fresh = ds._live_targets()
    # a day-old 0.4 pull has decayed well below its original strength
    assert not fresh or fresh[0][1] < 0.1


def test_next_target_skips_recent_and_yields_none_when_quiet(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ds.record_weakness([("바다는", 0.1)], floor=0.6)   # strong pull 0.5
    assert ds.next_target(recent=set()) == "바다"
    assert ds.next_target(recent={"바다"}) is None       # just visited → skip, nothing else pressing


def test_empty_state_is_none(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert ds.next_target(recent=set()) is None
    assert ds.status()["count"] == 0
