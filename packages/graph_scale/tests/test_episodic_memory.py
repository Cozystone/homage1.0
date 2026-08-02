# -*- coding: utf-8 -*-
"""Episodic memory: record lived multimodal moments, recall a vague '…' cue
into a predictive completion, surface what the glasses saw — and NEVER invent one.
"""
from datetime import datetime, timezone


def _reset(monkeypatch, tmp_path):
    from packages.graph_scale import episodic_memory as em
    monkeypatch.setattr(em, "LEDGER", tmp_path / "episodes.jsonl")
    return em


def test_record_recall_and_predictive_completion(tmp_path, monkeypatch):
    em = _reset(monkeypatch, tmp_path)
    em.record_episode(
        "모터쇼", ["자동차", "모터쇼", "전시"], at="2026-07-15T14:00:00", place="코엑스",
        observations=[em.Observation("vision", "신형 제네시스", salience=0.9)],
        salience=0.8)
    now = datetime(2027, 1, 10, tzinfo=timezone.utc)

    comp = em.complete("아 그때 그 우리 갔던 그 뭐더라", ["자동차"], now=now)
    assert comp is not None and comp["hypothesis"] is True
    assert "작년 7월" in comp["completion"] and "모터쇼" in comp["completion"]
    # the smart-glasses observation is surfaced (it was really recorded)
    assert comp["salient_observation"]["label"] == "신형 제네시스"
    assert "신형 제네시스" in comp["completion"]


def test_abstains_when_no_episode_matches(tmp_path, monkeypatch):
    em = _reset(monkeypatch, tmp_path)
    em.record_episode("모터쇼", ["자동차"], at="2026-07-15T14:00:00")
    # a cue about something never experienced -> abstain, not a fabricated memory
    assert em.complete("그때 그 우리 갔던", ["등산"]) is None
    assert em.recall(["등산"]) == []


def test_vision_slot_is_smart_glasses_ready(tmp_path, monkeypatch):
    em = _reset(monkeypatch, tmp_path)
    ep = em.record_episode("카페", ["커피"], at="2026-08-01T09:00:00")
    # the entry point smart glasses / a mic stream would call later
    assert em.add_observation(ep["episode_id"], "vision", "라떼아트", salience=0.7) is True
    assert em.add_observation(ep["episode_id"], "badmodality", "x") is False
    hits = em.recall(["라떼아트"])          # an observation label is itself recallable memory
    assert hits and hits[0]["title"] == "카페"


def test_interest_inferred_from_dwell_not_from_being_told(tmp_path, monkeypatch):
    em = _reset(monkeypatch, tmp_path)
    # a glance vs lingering: dwell time is the interest signal
    assert em.salience_from_behavior(1.0) < 0.2            # walked past — not interested
    assert em.salience_from_behavior(18.0) > 0.85          # lingered — clearly interested
    assert em.salience_from_behavior(6.0, revisits=2) > em.salience_from_behavior(6.0)
    ep = em.record_episode("모터쇼", ["자동차"], at="2026-07-15T14:00:00")
    # glasses report: user stood in front of the Genesis for 22s (never said a word)
    em.record_perception(ep["episode_id"], "신형 제네시스", dwell_seconds=22.0, revisits=1)
    hits = em.recall(["자동차"])
    obs = hits[0]["observations"][0]
    assert obs["salience"] >= 0.6 and obs["detail"]["inferred_from"] == "behavior"

    comp = em.complete("그때 그 우리 갔던", ["자동차"])
    assert "한참 보셨던 신형 제네시스" in comp["completion"]


def test_recall_prefers_salient_over_merely_recent(tmp_path, monkeypatch):
    em = _reset(monkeypatch, tmp_path)
    em.record_episode("잊은 약속", ["자동차"], at="2026-12-20T10:00:00", salience=0.1)
    em.record_episode("인상깊은 모터쇼", ["자동차"], at="2026-07-01T10:00:00", salience=0.95)
    now = datetime(2027, 1, 10, tzinfo=timezone.utc)
    hits = em.recall(["자동차"], now=now, k=2)
    assert hits[0]["title"] == "인상깊은 모터쇼"   # salience outweighs the small recency edge


def test_consolidation_forgets_trivial_old_keeps_salient(tmp_path, monkeypatch):
    """osaurus-style salience consolidation: a dull old moment fades; a vivid one
    persists. Salience governs MEMORY, not truth."""
    from datetime import datetime, timezone
    em = _reset(monkeypatch, tmp_path)
    em.record_episode("스치듯 본 간판", ["간판"], at="2026-01-01T10:00:00", salience=0.08)
    em.record_episode("인상깊은 모터쇼", ["자동차"], at="2026-01-01T10:00:00", salience=0.9)
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)   # ~6 months later
    r = em.consolidate(now=now)
    assert r["forgotten"] == 1 and r["kept"] == 1
    titles = {e["title"] for e in em._rows()}
    assert "인상깊은 모터쇼" in titles and "스치듯 본 간판" not in titles


def test_consolidation_merges_double_logged_episode(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    em = _reset(monkeypatch, tmp_path)
    a = em.record_episode("모터쇼", ["자동차"], at="2026-06-01T10:00:00", salience=0.8)
    em.record_perception(a["episode_id"], "제네시스", dwell_seconds=20)
    b = em.record_episode("모터쇼", ["자동차", "전시"], at="2026-06-01T10:30:00", salience=0.7)
    em.record_perception(b["episode_id"], "BMW", dwell_seconds=15)
    r = em.consolidate(now=datetime(2026, 6, 2, tzinfo=timezone.utc))
    assert r["merged"] == 1 and r["kept"] == 1
    ep = em._rows()[0]
    labels = {o["label"] for o in ep["observations"]}
    assert {"제네시스", "BMW"} <= labels          # both observations survive the merge
