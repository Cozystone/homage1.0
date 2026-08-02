# -*- coding: utf-8 -*-
"""Temporal KG: validity slices resolve by time; outside-interval = honest None."""
from __future__ import annotations

from packages.graph_scale import temporal_kg as tk


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(tk, "FACTS_PATH", tmp_path / "facts.jsonl")
    tk.assert_temporal("대한민국", "대통령", "문재인", "2017-05-10", "2022-05-09")
    tk.assert_temporal("대한민국", "대통령", "윤석열", "2022-05-10", "2025-04-04")
    tk.assert_temporal("대한민국", "대통령", "이재명", "2025-06-04", None)


def test_same_question_different_times_different_answers(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    assert tk.at_time("대한민국", "대통령", "2020")["object"] == "문재인"
    assert tk.at_time("대한민국", "대통령", "2023-01-01")["object"] == "윤석열"
    assert tk.current("대한민국", "대통령")["object"] == "이재명"


def test_gap_between_intervals_is_none_not_nearest(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    # the 2025-04-05 ~ 2025-06-03 vacancy: no valid officeholder — honest None
    assert tk.at_time("대한민국", "대통령", "2025-05-01") is None


def test_before_all_records_is_none(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    assert tk.at_time("대한민국", "대통령", "1990") is None


def test_timeline_is_ordered(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    tl = tk.timeline_of("대한민국", "대통령")
    assert [r["object"] for r in tl] == ["문재인", "윤석열", "이재명"]
