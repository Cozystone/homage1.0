# -*- coding: utf-8 -*-
"""The full round, and the termination that makes it a loop rather than a fixed pass count.

Two properties matter here and nowhere else: `foreign` must count as SETTLED (or the loop chases
the Athens that "the genitalia" belongs to forever), and the loop must stop itself when a round
settles nothing new.
"""
from __future__ import annotations

from packages.knowledge_repair.attribution import Referent
from packages.knowledge_repair.repair_loop import repair_round, repair_until_stalled

PLACES = [
    ("Athens", "defined_as", "A village in Claiborne Parish, Louisiana"),
    ("Athens", "defined_as", "A town in Somerset County, Maine"),
    ("Athens", "country", "Greece"),
]
UPSTAIRS = [
    ("Athens", "defined_as", "Located on a higher floor or level of a building"),
    ("Athens", "alias", "Up the stairs; on or to a higher floor or level"),
    ("Athens", "defined_as", "An upper storey of a building"),
]


def test_the_graph_alone_places_edges_without_any_source():
    """Graph-only is not a degraded mode -- on the measured node it was the richest source."""
    res, refs = repair_round("Athens", PLACES)
    assert res.referents >= 2                      # Louisiana, Maine read off the graph
    assert res.placed >= 2
    assert res.improved


def test_a_different_word_counts_as_settled_not_residue():
    res, _ = repair_round("Athens", PLACES + UPSTAIRS,
                          known=[Referent("Athens (Greece)", frozenset({"Greece"}))])
    assert res.foreign >= 3
    assert res.resolved == res.placed + res.foreign
    assert res.unresolved < len(UPSTAIRS)          # they left the residue


def test_the_loop_stops_when_a_round_settles_nothing_new():
    """Termination is the measurement, not a count. Round 2 can add no referent the graph did not
    already state, so it must end there rather than run to max_rounds."""
    rounds = repair_until_stalled("Athens", PLACES, max_rounds=6)
    assert len(rounds) < 6
    assert rounds[-1].stalled
    assert rounds[0].improved


def test_gain_is_measured_against_the_previous_round_not_zero():
    """And a round that settles FEWER than the last reports a negative gain rather than hiding it.

    (`country = Greece` is deliberately not placed here: the graph-derived referents are Louisiana
    and Maine, and nothing in these edges states a Greece referent. Not placing it is correct.)"""
    res, _ = repair_round("Athens", PLACES, resolved_before=2)
    assert res.resolved == 2 and res.gained == 0 and res.stalled

    dropped, _ = repair_round("Athens", PLACES, resolved_before=5)
    assert dropped.gained == -3                    # reported, not clamped to zero


def test_a_source_failure_does_not_fail_the_round():
    """The graph-only path must still run; a dead network is not a dead round."""
    class _Broken:
        def documents(self, *a, **k):
            raise RuntimeError("down")
    res, _ = repair_round("Athens", PLACES, evidence=_Broken())
    assert res.placed >= 2


def test_referents_carry_forward_between_rounds():
    _r1, refs1 = repair_round("Athens", PLACES, round_index=1)
    _r2, refs2 = repair_round("Athens", PLACES, known=refs1, round_index=2)
    assert len(refs2) >= len(refs1)
    assert {r.key for r in refs1} <= {r.key for r in refs2}


def test_open_questions_are_only_what_remains_genuinely_unknown():
    res, _ = repair_round("Athens", PLACES + [("Athens", "alias", "Athina")])
    assert any("Athina" in q for q in res.open_questions)
    assert not any("Louisiana" in q for q in res.open_questions)   # that one was placed
