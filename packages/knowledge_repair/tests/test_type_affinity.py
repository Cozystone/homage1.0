# -*- coding: utf-8 -*-
"""A1c: separate a merged name by KIND when there is no object text left to read.

The profiles below are hand-written because they are the INPUT to the algebra under test; the real
ones are read off the shipped graph by `type_profiles`, and every number here is a MEASURED
prevalence from the shipped store, so the test exercises the real shape rather than a flattering
one. In particular the grape is included with its real 0.179 `manufacturer`, because that is the
value that made the first version hand two shipyards to a grape.
"""
from __future__ import annotations

from packages.knowledge_repair.type_affinity import (
    TypeProfile, attribute_by_kind, discriminative, kind_referents, summarise_kinds,
    types_declared)

PAINTING = TypeProfile("painting", 491561,
                       {"is_a": 1.00, "located_in": 0.83, "creator": 0.785, "made_of": 0.735,
                        "genre": 0.39, "author": 0.019, "manufacturer": 0.005})
LITERARY = TypeProfile("literary work", 229786,
                       {"is_a": 1.00, "author": 0.829, "genre": 0.36, "country": 0.34,
                        "located_in": 0.06, "creator": 0.044, "manufacturer": 0.008})
HILL = TypeProfile("hill", 221043,
                   {"is_a": 1.00, "country": 1.00, "located_in": 0.86, "creator": 0.004,
                    "author": 0.002, "made_of": 0.003, "manufacturer": 0.002})
GRAPE = TypeProfile("hybrid grape", 223,
                    {"is_a": 1.00, "country": 0.48, "located_in": 0.40, "creator": 0.386,
                     "made_of": 0.161, "manufacturer": 0.179, "author": 0.143})
PROFILES = {"painting": PAINTING, "literary work": LITERARY, "hill": HILL}

RESIDUE = [
    ("Athens", "is_a", "painting"),
    ("Athens", "made_of", "canvas"),
    ("Athens", "creator", "Kenneth Hall"),
    ("Athens", "author", "Reinhard Stupperich"),
    ("Athens", "located_in", "Achaea"),
]


def test_candidate_kinds_come_only_from_what_the_node_claims():
    """No kind is invented: if the node never says it is a painting, no painting referent exists."""
    got = types_declared("Athens", RESIDUE + [("Athens", "is_a", "hill")])
    assert got == ["painting", "hill"]
    assert types_declared("Athens", [("Athens", "creator", "X")]) == []


def test_a_predicate_every_candidate_shares_says_nothing():
    """Paintings, hills and settlements are all `located_in` something, so it separates none of
    them however high its prevalence is."""
    everywhere = dict(PROFILES, **{"human settlement": TypeProfile(
        "human settlement", 328470, {"is_a": 1.00, "country": 1.00, "located_in": 0.96})})
    lifts = discriminative(everywhere)
    assert max(lifts[k]["located_in"] for k in everywhere) < 1.5
    (v,) = attribute_by_kind("Athens", [RESIDUE[4]], everywhere)
    assert v.outcome == "unknown" and "separates nothing" in v.basis


def test_a_property_no_candidate_kind_really_has_places_nothing():
    """The shipyard case, and the reason the absolute gate exists.

    `Athens` declares thirteen kinds and a ship is not one of them, so `manufacturer` has no right
    owner among them. Ranking alone still produces a winner -- 18% of hybrid grapes carry a
    manufacturer against 0.5% of paintings -- and the first real run duly handed two shipyards to a
    grape. Being the least unlike a ship is not being a ship."""
    with_grape = dict(PROFILES, **{"hybrid grape": GRAPE})
    (v,) = attribute_by_kind("Athens", [("Athens", "manufacturer", "Huanghai Shipbuilding")],
                             with_grape)
    assert v.outcome == "unknown"
    assert "really has this property" in v.basis


def test_a_property_typical_of_one_kind_places_the_edge():
    verdicts = {v.edge[1]: v for v in attribute_by_kind("Athens", RESIDUE, PROFILES)}
    assert verdicts["made_of"].referent == "Athens (painting)"
    assert verdicts["creator"].referent == "Athens (painting)"
    assert verdicts["author"].referent == "Athens (literary work)"


def test_the_declaring_predicate_is_never_attributed():
    """`is_a` produced the candidates; letting it also choose among them reads the answer off the
    question."""
    (v,) = attribute_by_kind("Athens", [RESIDUE[0]], PROFILES)
    assert v.outcome == "unknown" and "what the candidates were read from" in v.basis


def test_two_kinds_that_both_plausibly_own_it_stay_unknown():
    """A wrong placement is worse than an unplaced edge -- it looks resolved.

    The two gates catch different things and the test has to hit the SECOND one: `creator` here
    clears `min_lift` (it is genuinely uncommon for the third kind) but the two makers of things are
    too close to call, which is the case the margin exists for."""
    twins = {"painting": TypeProfile("painting", 100, {"creator": 0.90}),
             "sculpture": TypeProfile("sculpture", 100, {"creator": 0.75}),
             "hill": TypeProfile("hill", 100, {"creator": 0.02})}
    (v,) = attribute_by_kind("X", [("X", "creator", "someone")], twins)
    assert v.outcome == "unknown" and "about equally" in v.basis


def test_no_profiles_yields_no_verdicts_rather_than_guesses():
    got = attribute_by_kind("Athens", RESIDUE, {})
    assert {v.outcome for v in got} == {"unknown"}


def test_kinds_become_referents_the_rest_of_the_loop_understands():
    refs = {r.key for r in kind_referents("Athens", PROFILES)}
    assert "Athens (painting)" in refs and "Athens (hill)" in refs


def test_the_summary_names_which_kinds_attracted_edges():
    s = summarise_kinds(attribute_by_kind("Athens", RESIDUE, PROFILES))
    assert s["kinds"]["Athens (painting)"] == 2
    assert s["assigned"] == 3 and s["unknown"] == 2
