# -*- coding: utf-8 -*-
"""Composition: content from the graph, reading from a closed class, silence when neither fits."""
from __future__ import annotations

import numpy as np
import pytest

from packages.scene_model.compose import compose
from packages.scene_model.evaluate import evaluate


class _Store:
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
        self._t = triples
        self.terms = self._Terms(labels)
        self._c = {k: np.array([labels.index(r[i]) for r in triples], dtype="<i4")
                   for i, k in enumerate(("s", "p", "o"))}

    def open_columns(self): return self._c

    def facts_about(self, subject, limit=60):
        return [t for t in self._t if t[0] == subject][:limit]


WORLD = [
    ("France", "is_a", "Country"), ("France", "capital", "Paris"),
    ("Japan", "is_a", "Country"), ("Japan", "capital", "Tokyo"),
    ("Nauru", "is_a", "Country"),
    ("Paris", "is_a", "city"), ("Paris", "located_in", "France"),
    ("Tokyo", "is_a", "city"), ("Tokyo", "located_in", "Japan"),
    # a frequent function word the store really holds -- it must never win the head
    ("of", "is_a", "preposition"), ("of", "defined_as", "d1"), ("of", "defined_as", "d2"),
    ("of", "defined_as", "d3"), ("of", "defined_as", "d4"), ("of", "defined_as", "d5"),
]


@pytest.fixture()
def store():
    return _Store(WORLD)


def test_negative_existential_composes_and_answers(store):
    scene, why = compose("Which countries have no capital?", store)
    assert scene is not None, why
    assert scene.var_type == "Country" and scene.conditions[0].negated
    assert evaluate(scene, store)["members"] == ["Nauru"]


def test_the_same_composer_handles_a_plain_lookup(store):
    """One composer, two shapes -- the property a lane per shape cannot have."""
    scene, why = compose("What is the capital of France?", store)
    assert scene is not None, why
    assert scene.entity == "France" and scene.readout_predicate == "capital"
    assert evaluate(scene, store)["values"] == ["Paris"]


def test_a_frequent_function_word_never_wins_the_head(store):
    """Measured defect: `of` outranked `France` on raw degree, so every pairing scored 0 and the
    scene was about the preposition. Pairing coverage, not word frequency, decides."""
    scene, _ = compose("What is the capital of France?", store)
    assert scene.entity != "of"


def test_the_object_binds_only_when_some_member_actually_holds_it(store):
    """`which cities are located in Japan` binds Japan; `have` in another question binds nothing."""
    scene, why = compose("Which cities are located in Japan?", store)
    assert scene is not None, why
    assert scene.conditions[0].obj == "Japan"
    assert evaluate(scene, store)["members"] == ["Tokyo"]

    scene2, _ = compose("Which countries have no capital?", store)
    assert scene2.conditions[0].obj is None      # `have` is not an object anything carries


def test_counting_is_a_readout_not_a_different_engine(store):
    scene, why = compose("How many countries have a capital?", store)
    assert scene is not None, why
    assert evaluate(scene, store)["count"] == 2


def test_unknown_vocabulary_composes_nothing_and_says_why(store):
    """Fabrication is not an option: with no grounded relation there is no scene to evaluate."""
    scene, why = compose("Which flurbles have no snorgle?", store)
    assert scene is None and "relation" in why


def test_a_non_question_is_not_forced_into_a_scene(store):
    scene, why = compose("Hello, how are you?", store)
    assert scene is None and "readout" in why


def test_composition_is_subject_blind(store):
    """A type the composer has never seen works exactly as well, because nothing about the domain
    is written down -- this is what makes architecture questions ordinary once the census lands."""
    s = _Store(WORLD + [("deliberator", "is_a", "atanor_organ"),
                        ("deliberator", "has_a", "tests"),
                        ("scene_model", "is_a", "atanor_organ")])
    scene, why = compose("Which atanor organs have no tests?", s)
    assert scene is not None, why
    assert not scene.dropped_qualifiers        # nothing here is grounded EXCEPT the intended type
    assert evaluate(scene, s)["members"] == ["scene_model"]


def test_a_qualifier_the_scene_cannot_bind_is_recorded_not_silently_dropped():
    """Real bug, real graph, 2026-07-28: on the shipped store, `atanor` IS its own grounded
    entity (separate from the compound term `atanor_organ`) with real relational facts. Scene has
    one var_type slot, and the TYPE reading had more supporting coverage than the entity reading,
    so the composer bound `organ` -- a same-named but unrelated type -- and silently dropped
    `atanor`. This fixture reproduces exactly that shape at unit scale: `organ` (2 members with a
    `has_a` edge) outweighs `atanor` (coverage capped at 1, it is a single entity)."""
    s = _Store(WORLD + [
        ("atanor", "has_a", "deliberator"),                     # a REAL relational fact, not a gloss
        ("deliberator", "is_a", "organ"),                       # collides with an unrelated type
        ("heart", "is_a", "organ"), ("heart", "has_a", "valve"),
        ("lung", "is_a", "organ"), ("lung", "has_a", "alveolus"),
    ])
    scene, why = compose("Which atanor organs have no tests?", s)
    assert scene is not None, why
    assert scene.var_type == "organ"            # confirms this reproduces the real pairing, not a fluke
    assert "atanor" in scene.dropped_qualifiers
