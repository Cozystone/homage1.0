# -*- coding: utf-8 -*-
"""Noticing during USE, not auditing afterwards.

The distinction this file protects: an offline sweep ranks by severity and puts
`'Untitled'.creator = 2861 values` first -- real, but nobody asks. Recording as the conflict
BLOCKS AN ANSWER ranks by what actually gets in the way.
"""
from __future__ import annotations

import packages.knowledge_repair.conflict_ledger as C


def _redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", tmp_path / "conflicts.jsonl")


def test_a_blocked_answer_leaves_a_sighting(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    C.record_conflict("Athens", "country", ["Greece", "United States", "Canada"])
    got = C.standing_conflicts()
    assert len(got) == 1
    assert got[0].subject == "Athens"
    assert set(got[0].values) == {"Greece", "United States", "Canada"}


def test_repetition_is_the_ranking_signal(tmp_path, monkeypatch):
    """The same principle self_repair.defect_ledger uses for code -- but from its OWN use, not an
    advisor's report. A wall hit repeatedly outranks a bigger wall nobody walks into."""
    _redirect(tmp_path, monkeypatch)
    for _ in range(4):
        C.record_conflict("Athens", "country", ["Greece", "United States"])
    C.record_conflict("Untitled", "creator", [f"artist{i}" for i in range(9)])

    ranked = C.standing_conflicts()
    assert ranked[0].subject == "Athens" and ranked[0].hits == 4
    assert ranked[1].subject == "Untitled"       # far more values, but asked once


def test_the_ledger_never_picks_a_winner(tmp_path, monkeypatch):
    """The evidence that would settle it is not in the graph -- that is why acquisition exists."""
    _redirect(tmp_path, monkeypatch)
    C.record_conflict("Athens", "country", ["Greece", "United States"])
    top = C.standing_conflicts()[0]
    assert len(top.values) == 2                   # both kept, neither preferred
    assert not hasattr(top, "correct_value")
    assert "?" in top.as_question() and "Athens" in top.as_question()


def test_a_single_value_is_not_a_conflict(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    C.record_conflict("France", "capital", ["Paris"])
    C.record_conflict("France", "capital", ["Paris", "  "])     # blanks are not a second value
    assert C.standing_conflicts() == []


def test_recording_never_raises_even_when_the_sink_is_unwritable(tmp_path, monkeypatch):
    """Same contract as every other telemetry lane: the answer path must not fail because of it."""
    monkeypatch.setattr(C, "LEDGER", tmp_path / "a" / "b" / "c" / "conflicts.jsonl")
    monkeypatch.setattr(C.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
    C.record_conflict("X", "p", ["1", "2"])       # must not raise
