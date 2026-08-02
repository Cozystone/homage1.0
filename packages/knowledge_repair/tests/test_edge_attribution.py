# -*- coding: utf-8 -*-
"""A1b: three outcomes, because "I don't know which" and "this isn't that word" differ.

Measured on the real Athens node after A1a: of 135 unplaced edges, some name a referent nobody
acquired, some belong to a known referent whose marker the text does not repeat, and some are the
senses of "upstairs" merged under the same string. Collapsing the last into "unknown" would send
acquisition hunting forever for the Athens that "the genitalia" belongs to.
"""
from __future__ import annotations

from packages.knowledge_repair.attribution import Referent
from packages.knowledge_repair.edge_attribution import (
    attribute_edges, foreign_vocabulary, referents_from_edges, summarise)

GREECE = Referent("Athens (Greece)", frozenset({"Greece"}))
OHIO = Referent("Athens (Ohio)", frozenset({"Ohio"}))

# Shapes taken from the real node.
UPSTAIRS = [
    ("Athens", "defined_as", "Located on a higher floor or level of a building"),
    ("Athens", "alias", "Up the stairs; on or to a higher floor or level"),
    ("Athens", "defined_as", "An upper storey of a building"),
]
PLACES = [
    ("Athens", "defined_as", "A village in Claiborne Parish, Louisiana"),
    ("Athens", "defined_as", "A town in Somerset County, Maine"),
    ("Athens", "defined_as", "A city, the county seat of McMinn County, Tennessee"),
]


def test_the_graph_itself_supplies_referents_nobody_acquired():
    """Kind 1: for a merged node the object text of `defined_as` often IS a disambiguation entry."""
    got = {r.key for r in referents_from_edges("Athens", PLACES)}
    assert "Athens (Louisiana)" in got and "Athens (Maine)" in got and "Athens (Tennessee)" in got


def test_an_edge_naming_one_referent_is_assigned():
    edges = [("Athens", "country", "Greece")]
    (v,) = attribute_edges("Athens", edges, [GREECE, OHIO])
    assert v.placed and v.referent == "Athens (Greece)"


def test_a_known_referent_reached_only_by_an_acquired_alias_hint():
    """Kind 2: `Athina` is the Greek name; the module does not know that, acquisition supplies it."""
    edges = [("Athens", "alias", "Athina")]
    (no_hint,) = attribute_edges("Athens", edges, [GREECE, OHIO])
    assert no_hint.outcome == "unknown"          # correct: it genuinely does not know

    (hinted,) = attribute_edges("Athens", edges, [GREECE, OHIO],
                                alias_hints={"Athina": "Athens (Greece)"})
    assert hinted.placed and hinted.referent == "Athens (Greece)"


def test_another_word_sharing_the_surface_is_foreign_not_unknown():
    """Kind 3. Detected by a recurring vocabulary cluster that matches no referent -- structurally,
    not by naming 'upstairs' anywhere."""
    verdicts = attribute_edges("Athens", UPSTAIRS, [GREECE, OHIO])
    assert {v.outcome for v in verdicts} == {"foreign"}
    assert all("another word" in v.basis for v in verdicts)


def test_one_odd_definition_is_not_called_foreign():
    """Recurrence is what separates a second lexeme from noise; a single oddity stays unknown."""
    edges = [("Athens", "defined_as", "A surname from Greek origins")]
    (v,) = attribute_edges("Athens", edges, [OHIO])
    assert v.outcome == "unknown"


def test_foreign_vocabulary_ignores_words_a_referent_owns():
    edges = UPSTAIRS + [("Athens", "defined_as", "The capital of Greece and its largest city"),
                        ("Athens", "defined_as", "The Greece national government seat")]
    vocab = foreign_vocabulary(edges, [GREECE])
    assert "greece" not in vocab
    assert {"floor", "level"} & vocab


def test_foreign_counts_as_resolved_not_residue():
    """An edge that belongs to a different word is finished business -- it simply is not this
    node's. Leaving it in the residue would make the loop chase it forever."""
    verdicts = attribute_edges("Athens", UPSTAIRS + [("Athens", "country", "Greece")],
                               [GREECE, OHIO])
    s = summarise(verdicts)
    assert s["assigned"] == 1 and s["foreign"] == 3
    assert s["resolved"] == 4 and s["unknown"] == 0
    assert s["open_questions"] == []


def test_open_questions_are_only_the_genuinely_unknown():
    verdicts = attribute_edges("Athens", [("Athens", "alias", "Athina")], [GREECE])
    s = summarise(verdicts)
    assert s["unknown"] == 1 and len(s["open_questions"]) == 1
    assert "Athina" in s["open_questions"][0]
