# -*- coding: utf-8 -*-
"""Formulaic frame bank (S2.5a) — frames load, fill from slot values without inventing content, and
stay OUT of the reviewed-candidate promotion path (they are disclosed statistical skeletons)."""
from __future__ import annotations

from packages.construction_bank.frames import Frame, load_frames, fill_frame, best_frame


def test_frames_load():
    fs = load_frames()
    assert len(fs) >= 1000
    assert all(f.slots >= 1 for f in fs)                 # a frame always has at least one slot


def test_fill_drops_into_slots_in_order():
    f = Frame("the <SLOT> of <SLOT>", 2, 100, ())
    assert fill_frame(f, ["jazz", "New Orleans"]) == "The jazz of New Orleans"


def test_fill_never_invents_when_underfilled():
    f = Frame("<SLOT> is a <SLOT>", 2, 50, ())
    # only one value -> the unfilled slot is dropped, no hallucinated filler
    out = fill_frame(f, ["Quebec"])
    assert "Quebec" in out and out.count("<SLOT>") == 0


def test_best_frame_prefers_frequency():
    fs = load_frames()
    two = [f for f in fs if f.slots == 2]
    if two:
        assert best_frame(2).count == max(f.count for f in two)


def test_frames_are_not_reviewed_constructions():
    # frames carry no ConstructionCandidate promotion fields -> they cannot enter the human-review queue
    f = load_frames()[0]
    assert not hasattr(f, "status") and not hasattr(f, "production_active")
