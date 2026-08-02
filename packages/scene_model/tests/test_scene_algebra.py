# -*- coding: utf-8 -*-
"""The scene algebra: composition instead of query lanes, and honest about a non-closed world."""
from __future__ import annotations

import numpy as np
import pytest

from packages.scene_model.evaluate import evaluate, extension, project
from packages.scene_model.scene import Condition, Scene


class _Store:
    """A tiny interned store shaped like TripleStore: columns of ids + a term dict."""

    class _Terms:
        def __init__(self, labels): self._l = labels
        def term(self, i): return self._l[i]
        def lookup(self, t): return self._l.index(t) if t in self._l else None

    def __init__(self, triples):
        labels = []
        for row in triples:
            for x in row:
                if x not in labels:
                    labels.append(x)
        self.terms = self._Terms(labels)
        self._c = {k: np.array([labels.index(r[i]) for r in triples], dtype="<i4")
                   for i, k in enumerate(("s", "p", "o"))}

    def open_columns(self): return self._c


WORLD = [
    ("France", "is_a", "country"), ("France", "capital", "Paris"),
    ("Japan", "is_a", "country"), ("Japan", "capital", "Tokyo"),
    ("Nauru", "is_a", "country"),                       # genuinely no capital edge
    ("france", "is_a", "country"),                      # surface twin of France, no capital
    ("Paris", "is_a", "city"),
]


def test_the_same_evaluator_answers_lookup_and_negative_existential():
    """One organ, two question shapes. This is the whole point -- no lane per shape."""
    s = _Store(WORLD)
    lookup = evaluate(Scene(entity="France", readout="values", readout_predicate="capital"), s)
    assert lookup["ok"] and lookup["values"] == ["Paris"]

    absent = evaluate(Scene(var_type="country",
                            conditions=(Condition("capital", negated=True),)), s)
    assert absent["ok"] and set(absent["members"]) == {"Nauru", "france"}


def test_absence_is_flagged_as_a_closed_world_claim():
    """A graph is not the world. Absence must never surface as a universal claim unmarked."""
    s = _Store(WORLD)
    r = evaluate(Scene(var_type="country", conditions=(Condition("capital", negated=True),)), s)
    assert r["certificate"]["closed_world_assumption"] is True
    positive = evaluate(Scene(var_type="country", conditions=(Condition("capital"),)), s)
    assert positive["certificate"]["closed_world_assumption"] is False


def test_surface_twins_in_the_complement_are_reported_not_dropped():
    """Measured on the real graph: 53 of 158 'countries with no capital' were twins of a bearer.

    Reported, never subtracted -- subtracting would assert an identity the graph does not hold."""
    s = _Store(WORLD)
    cert = evaluate(Scene(var_type="country",
                          conditions=(Condition("capital", negated=True),)), s)["certificate"]
    assert cert["alias_suspects"] == ["france~France"]
    assert cert["alias_suspect_count"] == 1
    # Nauru has no twin and is therefore NOT flagged -- the signal must not smear over real gaps.
    assert not any(x.startswith("Nauru") for x in cert["alias_suspects"])


def test_a_type_the_graph_does_not_know_abstains_naming_the_unbound_part():
    s = _Store(WORLD)
    r = evaluate(Scene(var_type="unicorn", conditions=(Condition("capital", negated=True),)), s)
    assert not r["ok"] and "unicorn" in r["abstain"]


def test_coverage_is_reported_so_the_membrane_can_refuse():
    """Absence over a relation almost no peer carries is not evidence of anything."""
    s = _Store(WORLD)
    cert = evaluate(Scene(var_type="country",
                          conditions=(Condition("capital", negated=True),)), s)["certificate"]
    assert cert["relation_coverage"]["capital"] == pytest.approx(2 / 4)


def test_operators_compose_and_are_type_blind():
    """EXTENSION('country') and EXTENSION('atanor_organ') are the same call -- that is why the
    architecture questions need no new organ once the census is on the surface."""
    s = _Store(WORLD + [("deliberator", "is_a", "atanor_organ"),
                        ("deliberator", "has_a", "tests"),
                        ("scene_model", "is_a", "atanor_organ")])
    assert len(extension(s, "atanor_organ")) == 2
    assert len(project(s, extension(s, "atanor_organ"), "has_a")) == 1
    r = evaluate(Scene(var_type="atanor_organ",
                       conditions=(Condition("has_a", obj="tests", negated=True),)), s)
    assert r["ok"] and r["members"] == ["scene_model"]
