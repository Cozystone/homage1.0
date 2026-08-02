# -*- coding: utf-8 -*-
"""A round must be able to tell progress from motion.

Every other loop in this repository runs a fixed body for a fixed number of cycles and cannot say
whether a cycle helped. That is why none of them can decide to stop, notice being stuck, or be
handed to anything that would compose loops on its own.
"""
from __future__ import annotations

from packages.knowledge_repair.attribution import Referent, attribute
from packages.knowledge_repair.purification import acquisition_targets, purify_round

GREECE = Referent("Athens (Greece)", frozenset({"Greece", "Achaea"}))
OHIO = Referent("Athens (Ohio)", frozenset({"Ohio", "Athens County"}))

FACTS = [
    ("Athens", "country", "Greece"),
    ("Athens", "located_in", "Achaea"),
    ("Athens", "country", "United States"),
    ("Athens", "located_in", "Athens County"),
    ("Athens", "is_a", "cargo ship"),
]


def test_a_round_that_places_edges_is_an_improvement():
    r = purify_round("Athens", FACTS, [GREECE], [GREECE, OHIO], round_index=1)
    assert r.residue_before == 3 and r.residue_after == 2      # Athens County placed
    assert r.placed == 1
    assert r.improved and not r.stalled
    assert r.coverage_after > r.coverage_before


def test_learning_a_referent_that_places_nothing_is_not_an_improvement():
    """Motion, not progress: a new referent whose markers match no unplaced edge changed the
    knowledge and not the graph. Counting it as progress would let the loop congratulate itself
    forever."""
    useless = Referent("Athens (Zimbabwe)", frozenset({"Zimbabwe"}))
    r = purify_round("Athens", FACTS, [GREECE], [GREECE, useless])
    assert r.placed == 0
    assert not r.improved
    assert r.stalled                                            # nothing moved either way


def test_a_round_that_changes_nothing_is_stalled():
    r = purify_round("Athens", FACTS, [GREECE], [GREECE])
    assert r.stalled and not r.improved
    assert r.coverage_after == r.coverage_before


def test_residue_targets_use_the_contract_the_gap_ledger_already_consumes():
    """Merged-node residue enters through the EXISTING second endogenous source, not a third pipe
    -- a new pipe would be another path to maintain and to forget to wire."""
    a = attribute("Athens", FACTS, [GREECE])
    targets = acquisition_targets(a)
    assert targets
    for t in targets:
        assert set(t) >= {"gap_key", "question", "score", "pressure_sources", "curiosity"}
        assert t["pressure_sources"] == ["merge_residue"]
        assert t["question"].endswith("?")
    assert len({t["gap_key"] for t in targets}) == len(targets)   # keys are distinct


def test_the_round_record_is_serialisable_for_a_ledger():
    r = purify_round("Athens", FACTS, [GREECE], [GREECE, OHIO], round_index=2)
    d = r.as_dict()
    assert d["round"] == 2 and d["placed"] == 1 and d["improved"] is True
    assert 0.0 <= d["coverage_after"] <= 1.0
