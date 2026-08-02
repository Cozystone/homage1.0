# -*- coding: utf-8 -*-
"""ATMS (de Kleer 1986) -- tier environments, nogoods, safe/creative modes.

Required tests:
 (b) a fact contradicting a T0 fact under {neural} -> that env becomes nogood ->
     the neural fact auto-invalidated; the T0 core is untouched.
 (c) same store, query under {T0} (safe) omits a neural-only fact that a
     {T0, neural} (creative) query returns.
"""
from __future__ import annotations

from packages.truth_maintenance.atms import ATMS, T0, NEURAL, CONSENSUS


def test_b_neural_contradicting_t0_is_invalidated_core_untouched():
    a = ATMS(core=(T0,))
    # operator ground truth: capital(france)=paris  under {T0}
    a.assume("capital(france)=paris", {T0})
    # neural proposal contradicting it: capital(france)=berlin  under {neural}
    a.assume("capital(france)=berlin", {NEURAL})

    nogoods = a.register_contradiction("capital(france)=paris", "capital(france)=berlin")
    # the joint environment {T0, neural} is recorded as a nogood
    assert frozenset({T0, NEURAL}) in a.nogoods()
    assert frozenset({T0, NEURAL}) in nogoods

    # the neural fact cannot hold alongside the ever-present operator core -> invalid
    assert a.invalidated("capital(france)=berlin") is True
    # the T0 core is untouched
    assert a.invalidated("capital(france)=paris") is False
    assert a.safe_query("capital(france)=paris") is True


def test_b_datum_supported_only_by_nogood_env_auto_invalidated():
    # direct nogood on the {neural} env itself empties any neural-only label.
    a = ATMS(core=(T0,))
    a.assume("shaky_neural_fact", {NEURAL})
    assert a.valid("shaky_neural_fact")
    a.mark_nogood({NEURAL})                      # the neural env is declared inconsistent
    assert a.label("shaky_neural_fact") == set()  # pruned to empty
    assert a.invalidated("shaky_neural_fact") is True


def test_c_safe_omits_creative_returns_neural_only_fact():
    a = ATMS(core=(T0,))
    a.assume("operator_fact", {T0})
    a.assume("neural_only_fact", {NEURAL})       # no contradiction: a clean neural proposal

    # safe mode: query under {T0} only
    assert a.safe_query("operator_fact") is True
    assert a.safe_query("neural_only_fact") is False       # omitted in safe mode

    # creative mode: query under {T0, neural}
    assert a.creative_query("neural_only_fact") is True     # returned in creative mode
    assert a.creative_query("operator_fact") is True

    # "context switching is free": same store, two contexts, no re-derivation
    assert a.context({T0}) == ["operator_fact"]
    assert a.context({T0, NEURAL}) == ["neural_only_fact", "operator_fact"]


def test_label_minimality_subsumption():
    a = ATMS(core=(T0,))
    a.assume("f", {NEURAL})
    a.assume("f", {NEURAL, CONSENSUS})   # superset -> subsumed, dropped
    assert a.label("f") == {frozenset({NEURAL})}


def test_nogood_superset_closure():
    a = ATMS(core=(T0,))
    a.mark_nogood({NEURAL})
    # any superset of a nogood is a nogood
    assert a.is_nogood({NEURAL, CONSENSUS}) is True
    assert a.is_nogood({CONSENSUS}) is False


def test_holds_under_requires_consistent_context():
    a = ATMS(core=(T0,))
    a.assume("x", {NEURAL})
    a.mark_nogood({T0, NEURAL})
    # context {T0, neural} is inconsistent -> nothing holds there
    assert a.holds_under("x", {T0, NEURAL}) is False
    assert a.context({T0, NEURAL}) == []
