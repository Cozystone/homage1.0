# -*- coding: utf-8 -*-
"""What the image-schema organs must keep doing. Written after the fact, which is late but not too late.

These lock the properties the design rests on rather than the numbers a run happened to produce:
domain-blindness, abstention where a measurement is impossible, polarity as ONE integer, the inverse
index being derived from the speaker, MDL preferring the structure the grammar explains more of, and
the collision that cost half a benchmark today.
"""
from __future__ import annotations

import pytest

from packages.image_schema import (Containment, MetricScene, Path, Possession, Proximity,
                                   SymbolicScene, Transfer, choose, satisfaction)
from packages.image_schema.inverse_speaker import InverseSpeaker, norm


# ---------------------------------------------------------------- the basis
def test_one_schema_object_runs_over_both_worlds():
    """A primitive that needs a different implementation per domain is not a primitive."""
    sym = SymbolicScene(at={"a": "office", "b": "kitchen"},
                        adj={"office": ["hall"], "hall": ["office", "kitchen"], "kitchen": ["hall"]})
    met = MetricScene(pos={"a": (0.0, 0.0), "b": (30.0, 40.0), "c": (10.0, 0.0)})
    s = Proximity("a", "b")
    assert s.signed(sym) is not None
    assert s.signed(met) is not None


def test_abstains_rather_than_inventing_a_measurement():
    """A metric world has no rooms and no holders; the schema must say so, not approximate."""
    met = MetricScene(pos={"a": (0.0, 0.0), "b": (5.0, 0.0)})
    assert Path("a", "kitchen").signed(met) is None
    assert Possession("a", "b").signed(met) is None
    assert Transfer("a", "b", "c").signed(met) is None


def test_polarity_is_one_integer_and_flips_the_preference():
    """approach and avoid are the same schema with the sign of Talmy's tendency reversed."""
    near = MetricScene(pos={"me": (0.0, 0.0), "x": (2.0, 0.0), "far": (400.0, 0.0)})
    a = Proximity("me", "x", polarity=+1).signed(near)
    b = Proximity("me", "x", polarity=-1).signed(near)
    assert a is not None and b is not None
    assert a + b == pytest.approx(1.0)
    assert a > b


def test_conjunction_is_the_weakest_link_not_the_average():
    """An instruction is met when ALL of it is met; an average lets one clause pay for another."""
    sc = MetricScene(pos={"me": (0.0, 0.0), "x": (1.0, 0.0), "y": (500.0, 0.0)})
    both = satisfaction([Proximity("me", "x"), Proximity("me", "y")], sc)
    assert both == pytest.approx(min(Proximity("me", "x").signed(sc),
                                     Proximity("me", "y").signed(sc)))


def test_executor_picks_by_predicted_future_and_polarity_reverses_it():
    """The whole coupling between an instruction and behaviour, with no reward anywhere in it."""
    sc = MetricScene(pos={"me": (0.0, 0.0), "x": (10.0, 0.0)})

    def rollout(scene, action):
        d = {"left": (-5.0, 0.0), "right": (5.0, 0.0)}[action]
        return MetricScene(pos={k: (p[0] + (d[0] if k == "me" else 0.0), p[1])
                                for k, p in scene._pos.items()})

    assert choose(["left", "right"], rollout, [Proximity("me", "x", polarity=+1)], sc)[0] == "right"
    assert choose(["left", "right"], rollout, [Proximity("me", "x", polarity=-1)], sc)[0] == "left"


def test_containment_prefers_the_domain_fact_over_the_distance_fallback():
    sym = SymbolicScene(at={"apple": "kitchen"})
    assert Containment("apple", "kitchen").signed(sym) == 1.0
    assert Containment("apple", "office").signed(sym) == 0.0


# ---------------------------------------------------------------- the inverse
def test_index_is_derived_from_the_speaker_not_written():
    inv = InverseSpeaker(["is_a", "alias", "part_of"])
    assert inv.fwd["is_a"] and inv.fwd["part_of"]
    assert any("part of" in m for m in inv.fwd["part_of"])


def test_understanding_regenerates_or_abstains():
    inv = InverseSpeaker(["is_a", "alias", "part_of"])
    assert inv.best("A wheel is part of a car.")[0] is not None
    assert inv.best("Colourless green ideas sleep furiously.")[0] is None


def test_mdl_prefers_the_structure_the_grammar_explains_more_of():
    """is_a and has_property both regenerate 'X is a Y'; the one whose frame consumed the determiner
    leaves less in its arguments and must win."""
    inv = InverseSpeaker(["is_a", "has_property"])
    best, n = inv.best("Albedo is a ratio.")
    assert best is not None and n >= 1
    assert best[1] == "is_a"


def test_a_construction_may_not_be_claimed_by_two_relations():
    """The collision that took self-speech from 74.0% to 31.2% today, locked out as a property.

    `alias` -> '{s} is a {o}' regenerates every 'X is a Y' that is_a already owns, so two structures
    with identical argument lengths become indistinguishable to MDL.
    The CURATED set already collides -- is_a and instance_of are near-synonyms and share
    '{s} is {det} {o}' -- and that predates today. What the guard promises, and what is asserted here,
    is narrower and is the part that was actually costing: an ACQUIRED construction must not take a
    surface form that a DIFFERENT relation's curated frame already owns."""
    from packages.realizer_struct.frame_realizer import FRAMES
    curated = {}
    for rel, f in FRAMES.items():
        mid = norm(f["tmpl"][4:-4]) if f["tmpl"].startswith("{s}") else ""
        if mid:
            curated.setdefault(mid, rel)
    for rel, f in FRAMES.items():
        for alt in f.get("alts", []):
            if not alt.startswith("{s}"):
                continue
            mid = norm(alt[4:-4])
            owner = curated.get(mid)
            assert owner in (None, rel), (
                f"acquired {alt!r} for {rel!r} collides with {owner!r}'s curated frame")


def test_the_speaker_actually_loaded_its_acquired_constructions():
    """Built-but-not-wired guard: nine live modules import the realizer and none called the loader."""
    from packages.realizer_struct.frame_realizer import constructions
    assert len(constructions("is_a")) > 1, "acquired constructions are not installed at import"
