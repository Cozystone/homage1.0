# -*- coding: utf-8 -*-
"""Splitting a merged node honestly: place what the evidence places, report the rest.

The failure this guards against is a split that LOOKS complete. A merged node is visibly wrong;
a confidently mis-split one is not, which makes it worse.
"""
from __future__ import annotations

from packages.knowledge_repair.attribution import Attribution, Referent, attribute

GREECE = Referent("Athens (Greece)", frozenset({"Greece", "Attica", "Achaea"}))
OHIO = Referent("Athens (Ohio)", frozenset({"United States", "Ohio", "Athens County"}))

ATHENS_FACTS = [
    ("Athens", "country", "Greece"),
    ("Athens", "located_in", "Achaea"),
    ("Athens", "country", "United States"),
    ("Athens", "located_in", "Athens County"),
    ("Athens", "is_a", "cargo ship"),                    # no marker names either referent
    ("Athens", "located_in", "Auckland Art Gallery"),    # nor this
]


def test_edges_whose_evidence_names_one_referent_are_placed():
    a = attribute("Athens", ATHENS_FACTS, [GREECE, OHIO])
    assert ("Athens", "country", "Greece") in a.assigned["Athens (Greece)"]
    assert ("Athens", "located_in", "Achaea") in a.assigned["Athens (Greece)"]
    assert ("Athens", "country", "United States") in a.assigned["Athens (Ohio)"]


def test_edges_with_no_evidence_are_left_unassigned_not_guessed():
    """The cargo ship and the art gallery belong to neither known referent. Assigning them to the
    larger or nearer one would fabricate structure."""
    a = attribute("Athens", ATHENS_FACTS, [GREECE, OHIO])
    assert ("Athens", "is_a", "cargo ship") in a.unassigned
    assert ("Athens", "located_in", "Auckland Art Gallery") in a.unassigned


def test_coverage_reports_how_partial_the_split_actually_is():
    a = attribute("Athens", ATHENS_FACTS, [GREECE, OHIO])
    assert a.total == 6
    assert len(a.unassigned) == 2
    assert a.coverage == 4 / 6                # a partial split that says so


def test_evidence_naming_two_referents_is_contested_not_silently_picked():
    """Ambiguous evidence is a different problem from missing evidence: it means the marker sets
    need refining, not that facts are missing. Collapsing the two would hide which to fix."""
    overlapping = Referent("Athens (Georgia US)", frozenset({"United States", "Georgia"}))
    a = attribute("Athens", [("Athens", "country", "United States")], [OHIO, overlapping])
    assert a.contested == (("Athens", "country", "United States"),)
    assert not a.assigned


def test_residual_questions_name_one_unplaced_edge_each():
    """So a later acquisition round can measurably shrink the residue instead of restating the
    whole problem."""
    a = attribute("Athens", ATHENS_FACTS, [GREECE, OHIO])
    qs = a.residual_questions()
    assert len(qs) == 2
    assert any("cargo ship" in q for q in qs)
    assert all(q.endswith("?") for q in qs)


def test_no_referents_means_nothing_is_placed_and_coverage_is_zero():
    """Before acquisition has found out what the referents ARE, the honest answer is that no edge
    can be placed -- not that they all belong to one thing."""
    a = attribute("Athens", ATHENS_FACTS, [])
    assert a.assigned == {} and a.coverage == 0.0
    assert len(a.unassigned) == len(ATHENS_FACTS)
