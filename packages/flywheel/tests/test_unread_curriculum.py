# -*- coding: utf-8 -*-
"""The curriculum lane: what the composer could not READ, ranked by how often it blocked traffic.

Distinct from failures.jsonl on purpose. A failure is "I answered and was wrong, or abstained".
An unread is "I could not form the question at all" -- the only signal that names a missing
REPRESENTATION rather than missing knowledge.
"""
from __future__ import annotations

import json

import packages.flywheel.logger as L


def _redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "FLYWHEEL_DIR", tmp_path)
    monkeypatch.setattr(L, "UNREAD_PATH", tmp_path / "unread.jsonl")


def test_an_unread_question_is_recorded_with_its_reason(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    L.log_unread("which glorbnaks have no snurfle?", "no span names a relation the graph uses",
                 organ="scene_model.compose")
    rows = [json.loads(x) for x in (tmp_path / "unread.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["q"] == "which glorbnaks have no snurfle?"
    assert "relation" in rows[0]["reason"]
    assert rows[0]["organ"] == "scene_model.compose"


def test_the_curriculum_ranks_by_how_often_a_reason_blocked_a_question(tmp_path, monkeypatch):
    """What to widen next is not a judgement call -- it is whatever traffic keeps hitting."""
    _redirect(tmp_path, monkeypatch)
    for _ in range(3):
        L.log_unread("q1", "no readout marker", organ="scene_model.compose")
    L.log_unread("q2", "qualifier had nowhere to bind", organ="scene_model.compose")

    ranked = L.unread_curriculum()
    assert [r["reason"] for r in ranked] == ["no readout marker", "qualifier had nowhere to bind"]
    assert ranked[0]["count"] == 3
    assert ranked[0]["example"] == "q1"


def test_a_missing_log_is_an_empty_curriculum_not_a_crash(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    assert L.unread_curriculum() == []


def test_logging_never_raises_even_when_the_sink_is_unwritable(tmp_path, monkeypatch):
    """Same contract as log_turn: the chat path must not be able to fail because of telemetry."""
    monkeypatch.setattr(L, "FLYWHEEL_DIR", tmp_path / "nope")
    monkeypatch.setattr(L, "UNREAD_PATH", tmp_path / "nope" / "x" / "y" / "unread.jsonl")
    L.log_unread("q", "reason")            # must not raise
