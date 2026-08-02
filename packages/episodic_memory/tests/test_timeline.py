# -*- coding: utf-8 -*-
"""Episodic time-axis graph: dated events, honest ages, the primitive."""
from __future__ import annotations

# the package __init__ re-exports a FUNCTION named `timeline`, shadowing the
# module attribute — go through sys.modules for the real module object
import importlib

tl_mod = importlib.import_module("packages.episodic_memory.timeline")


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(tl_mod, "EVENTS_PATH", tmp_path / "events.jsonl")


def test_record_and_age(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    tl_mod.record_event("사용자", "구매", "물병", at="2023-07-08", note="스텐 500ml")
    days = tl_mod.age_days("사용자", "구매", "물병")
    assert days is not None and days > 1000  # ~3 years


def test_unknown_age_is_none_never_guessed(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    assert tl_mod.age_days("사용자", "구매", "우산") is None


def test_repurchase_suggestion_fires_only_past_threshold(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    tl_mod.record_event("사용자", "구매", "물병", at="2023-07-08")
    s = tl_mod.repurchase_suggestion("물병", threshold_days=900)
    assert s is not None and "물병" in s["suggestion"] and s["age_days"] > 900
    assert s["basis"]  # grounded in the recorded event
    tl_mod.record_event("사용자", "구매", "텀블러")  # bought today
    assert tl_mod.repurchase_suggestion("텀블러", threshold_days=900) is None


def test_timeline_orders_events(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    tl_mod.record_event("사용자", "구매", "물병", at="2023-07-08")
    tl_mod.record_event("사용자", "수리", "물병 뚜껑", at="2025-01-02")
    tl = tl_mod.timeline("물병")
    assert len(tl) == 2 and tl[0]["at"] < tl[1]["at"]
