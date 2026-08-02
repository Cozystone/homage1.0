# -*- coding: utf-8 -*-
"""Defeasible reasoning (Reiter 1980 + Pollock 1987) -- the M3 blind-spot path.

Required test (e): an inheritance default (penguin is_a bird -> can_fly) is
undercut by an exception (penguin cannot_fly) -> status withdrawn, negation NOT
asserted.
"""
from __future__ import annotations

from packages.truth_maintenance.defeasible import (
    DefeasibleReasoner, WITHDRAWN, undercut_node,
)
from packages.truth_maintenance.jtms import IN, OUT


def test_e_inheritance_default_undercut_by_exception():
    r = DefeasibleReasoner()
    # inheritance default: penguin is_a bird, bird can_fly  ~>  penguin can_fly
    conclusion = r.add_inheritance_default("penguin", "bird", "can_fly")
    assert conclusion == "can_fly(penguin)"
    assert r.status(conclusion) == IN            # default holds before the exception

    # graph-encoded exception: penguin cannot_fly (an undercutting defeater)
    r.add_exception("penguin", "can_fly", marker="cannot_fly(penguin)")

    # the inherited default's WARRANT is withdrawn ...
    assert r.status(conclusion) == WITHDRAWN
    assert r.is_warranted(conclusion) is False
    # ... and the reasoner asserted NO negation (undercutting, not rebutting)
    assert r.asserted_negations() == set()


def test_e_undercutter_flips_defeater_node_in():
    r = DefeasibleReasoner()
    c = r.add_inheritance_default("penguin", "bird", "can_fly")
    assert r.jtms.status(undercut_node(c)) == OUT     # no defeater yet
    r.add_exception("penguin", "can_fly", marker="cannot_fly(penguin)")
    assert r.jtms.status(undercut_node(c)) == IN      # defeater fired


def test_default_without_exception_stays_in():
    r = DefeasibleReasoner()
    c = r.add_inheritance_default("sparrow", "bird", "can_fly")
    assert r.status(c) == IN
    assert r.asserted_negations() == set()


def test_rebutter_contrast_does_assert_negation():
    # contrast: a REBUTTING defeater asserts the opposite -- the behaviour
    # undercutting deliberately avoids.
    r = DefeasibleReasoner()
    c = r.add_inheritance_default("penguin", "bird", "can_fly")
    r.add_rebutter(c, negation="cannot_fly(penguin)")
    assert r.status(c) == WITHDRAWN
    assert r.asserted_negations() == {"cannot_fly(penguin)"}   # negation IS asserted


def test_exception_marker_recorded_as_fact_not_negation():
    # the exception marker is a real stored fact (audit trail) but is NOT routed
    # into the reasoner's derived-negation set.
    r = DefeasibleReasoner()
    r.add_inheritance_default("penguin", "bird", "can_fly")
    r.add_exception("penguin", "can_fly", marker="cannot_fly(penguin)")
    assert r.jtms.is_in("cannot_fly(penguin)")       # marker present in the graph
    assert r.asserted_negations() == set()           # but reasoner asserted no negation


def test_removing_exception_restores_default():
    r = DefeasibleReasoner()
    c = r.add_inheritance_default("penguin", "bird", "can_fly")
    r.add_exception("penguin", "can_fly", marker="cannot_fly(penguin)")
    assert r.status(c) == WITHDRAWN
    r.jtms.retract(undercut_node(c))                 # exception withdrawn
    assert r.status(c) == IN                          # warrant restored
