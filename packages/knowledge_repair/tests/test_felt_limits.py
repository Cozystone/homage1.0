# -*- coding: utf-8 -*-
"""A limit noticed during use must reach the drive that can act on it.

The gap this closes: `deficit.compute_deficit` reads `WorldModelSnapshot.contradictions`, and the
summary that fills it was built from sources that never heard of the conflict ledger. Limits were
felt, recorded, and never seen by anything that allocates effort.
"""
from __future__ import annotations

import packages.knowledge_repair.conflict_ledger as CL
import packages.flywheel.logger as FL
from packages.knowledge_repair.felt_limits import (
    limits_as_contradictions, limits_as_unresolved, merge_into_world_summary)


def _ledgers(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "LEDGER", tmp_path / "conflicts.jsonl")
    monkeypatch.setattr(FL, "FLYWHEEL_DIR", tmp_path)
    monkeypatch.setattr(FL, "UNREAD_PATH", tmp_path / "unread.jsonl")


def test_a_conflict_becomes_a_contradiction_the_deficit_organ_can_read(tmp_path, monkeypatch):
    _ledgers(tmp_path, monkeypatch)
    CL.record_conflict("Athens", "country", ["Greece", "United States", "Canada"])
    (c,) = limits_as_contradictions()
    assert c["subject"] == "Athens" and c["competing_values"] == 3
    assert 0.0 < c["severity"] <= 1.0
    assert "?" in c["question"]


def test_severity_follows_how_often_it_blocked_an_answer_not_its_size(tmp_path, monkeypatch):
    """A node tripped over repeatedly outranks a bigger one nobody asks about -- the same ordering
    the ledger uses, carried through rather than re-derived."""
    _ledgers(tmp_path, monkeypatch)
    for _ in range(4):
        CL.record_conflict("Athens", "country", ["Greece", "United States"])
    CL.record_conflict("Untitled", "creator", [f"a{i}" for i in range(9)])

    by = {c["subject"]: c for c in limits_as_contradictions()}
    assert by["Athens"]["severity"] > by["Untitled"]["severity"]
    assert by["Untitled"]["competing_values"] > by["Athens"]["competing_values"]


def test_severity_saturates_so_one_signal_cannot_dominate(tmp_path, monkeypatch):
    _ledgers(tmp_path, monkeypatch)
    for _ in range(200):
        CL.record_conflict("Athens", "country", ["Greece", "United States"])
    assert limits_as_contradictions()[0]["severity"] <= 1.0


def test_unread_questions_stay_separate_from_contradictions(tmp_path, monkeypatch):
    """They call for different training -- acquisition vs widening the composer -- so merging them
    into one bucket would send the drive to the wrong gym."""
    _ledgers(tmp_path, monkeypatch)
    CL.record_conflict("Athens", "country", ["Greece", "United States"])
    FL.log_unread("tell me a story", "no readout marker", organ="scene_model.compose")

    assert len(limits_as_contradictions()) == 1
    assert len(limits_as_unresolved()) == 1
    assert "readout" in limits_as_unresolved()[0]


def test_merging_is_additive_and_does_not_mutate_the_caller(tmp_path, monkeypatch):
    _ledgers(tmp_path, monkeypatch)
    CL.record_conflict("Athens", "country", ["Greece", "United States"])
    original = {"concepts": 5, "contradictions": [{"kind": "pre_existing"}]}

    merged = merge_into_world_summary(original)
    assert merged["concepts"] == 5
    assert {c.get("kind") for c in merged["contradictions"]} == {"pre_existing", "merged_referent"}
    assert original["contradictions"] == [{"kind": "pre_existing"}]      # untouched


def test_empty_ledgers_add_nothing(tmp_path, monkeypatch):
    _ledgers(tmp_path, monkeypatch)
    merged = merge_into_world_summary({"concepts": 1})
    assert merged["contradictions"] == [] and merged["unresolved_questions"] == []
