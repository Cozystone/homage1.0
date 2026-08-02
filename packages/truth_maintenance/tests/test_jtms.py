# -*- coding: utf-8 -*-
"""JTMS (Doyle 1979) -- dependency-directed retraction.

Required test (a): add A justified by source S; add B derived from A; retract S
-> both A and B auto-OUT.
"""
from __future__ import annotations

from packages.truth_maintenance.jtms import JTMS, IN, OUT


def _chain() -> JTMS:
    j = JTMS()
    j.add_premise("S", informant="source")                       # premise (external assertion)
    j.add_justified("A", support=["S"], informant="derive_A")    # A justified by S
    j.add_justified("B", support=["A"], informant="derive_B")    # B derived from A
    return j


def test_a_retract_source_flips_all_descendants_out():
    j = _chain()
    assert j.is_in("S") and j.is_in("A") and j.is_in("B")

    j.retract("S")   # source invalidated

    # dependency-directed retraction: A and B flip OUT automatically, no sweep
    assert j.status("S") == OUT
    assert j.status("A") == OUT
    assert j.status("B") == OUT


def test_premise_and_derived_labels():
    j = _chain()
    assert j.beliefs() == ["A", "B", "S"]
    exp = j.explanation("B")
    assert exp["status"] == IN
    assert exp["informant"] == "derive_B"
    # well-founded: B <- A <- S
    assert exp["in"]["A"]["in"]["S"]["status"] == IN


def test_no_justification_is_out():
    j = JTMS()
    j.node("orphan")
    assert j.status("orphan") == OUT


def test_reasserting_source_restores_beliefs():
    j = _chain()
    j.retract("S")
    assert not j.is_in("B")
    j.add_premise("S", informant="source")   # source returns
    assert j.is_in("A") and j.is_in("B")      # beliefs restored by relabelling


def test_multiple_supports_one_survives():
    # A supported by two independent sources; retracting one keeps A IN.
    j = JTMS()
    j.add_premise("S1", informant="src1")
    j.add_premise("S2", informant="src2")
    j.add_justified("A", support=["S1"], informant="d1")
    j.add_justified("A", support=["S2"], informant="d2")
    j.add_justified("B", support=["A"], informant="dB")
    assert j.is_in("B")
    j.retract("S1")
    assert j.is_in("A") and j.is_in("B")     # S2 still supports A
    j.retract("S2")
    assert j.status("A") == OUT and j.status("B") == OUT   # now fully unsupported


def test_invalidate_informant_returns_flipped():
    j = _chain()
    flipped = j.invalidate_informant("source")   # the source informant is gone
    # S loses its premise -> A, B lose support
    assert set(flipped) == {"S", "A", "B"}
