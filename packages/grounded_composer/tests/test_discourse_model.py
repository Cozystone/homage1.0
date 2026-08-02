# -*- coding: utf-8 -*-
"""Learned discourse model: closed vocabulary, learned ranking, graceful absence."""
from __future__ import annotations

import json

from packages.grounded_composer import discourse_model as dm


def test_picks_stay_inside_approved_whitelist(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "STATS_PATH", tmp_path / "stats.json")
    dm._STATS["freq"] = None
    (tmp_path / "stats.json").write_text(json.dumps({
        "freq": {"그리고": 30, "특히": 20, "또한": 10},
        "trans": {}}), encoding="utf-8")
    picks = [dm.pick_connective(i, None) for i in range(6)]
    assert all(p in dm.APPROVED_MARKERS for p in picks)


def test_no_immediate_repetition(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "STATS_PATH", tmp_path / "stats.json")
    dm._STATS["freq"] = None
    (tmp_path / "stats.json").write_text(json.dumps({
        "freq": {"그리고": 30, "또한": 10}, "trans": {}}), encoding="utf-8")
    assert dm.pick_connective(0, prev="그리고") != "그리고"


def test_absent_stats_mean_no_opinion(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "STATS_PATH", tmp_path / "missing.json")
    dm._STATS["freq"] = None
    assert dm.pick_connective(0) is None  # composer keeps its static default
