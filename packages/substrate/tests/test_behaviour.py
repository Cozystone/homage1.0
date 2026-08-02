# -*- coding: utf-8 -*-
"""V7-0: behaviour-derived coordinates, and the three ways this measurement could have been fake."""
from __future__ import annotations

from packages.substrate.behaviour import (
    behaviour_of, distance, read_signal, shared_basis, shuffled)

PAINTING_A = [("a", "is_a", "painting"), ("a", "creator", "X"), ("a", "made_of", "oil"),
              ("a", "made_of", "canvas"), ("a", "genre", "portrait")]
PAINTING_B = [("b", "is_a", "painting"), ("b", "creator", "Y"), ("b", "made_of", "canvas"),
              ("b", "genre", "landscape")]
HILL_A = [("h", "is_a", "hill"), ("h", "country", "Nepal"), ("h", "located_in", "Region")]
HILL_B = [("i", "is_a", "hill"), ("i", "country", "Peru"), ("i", "located_in", "Andes")]


def test_the_kind_declaration_is_excluded_or_the_vector_answers_the_question():
    """Leaving `is_a` in would put an entity near its kind-mates because both SAY they are that
    kind. That is the label, not behaviour, and the gate asks about behaviour."""
    b = behaviour_of("a", PAINTING_A)
    assert "is_a" not in b.shares
    assert set(b.shares) == {"creator", "made_of", "genre"}


def test_a_behaviour_is_a_distribution_not_a_count():
    """Raw counts measure how well DOCUMENTED a thing is. The same error at kind level made a
    223-member grape class swallow two shipyards before prevalence replaced rate."""
    b = behaviour_of("a", PAINTING_A)
    assert abs(sum(b.shares.values()) - 1.0) < 1e-9
    # the same shape, documented twice as heavily, is the same point
    doubled = [(s, p, o + "2") for s, p, o in PAINTING_A] + PAINTING_A
    assert distance(b, behaviour_of("a", doubled), ["creator", "made_of", "genre"]) < 0.05


def test_a_global_relabelling_cannot_serve_as_the_control():
    """It is an ISOMETRY -- every pairwise distance is preserved -- so it reproduces the real
    separation exactly. The first version of this control did that and made the gate structurally
    incapable of reading anything but FAIL."""
    basis = ["creator", "made_of", "genre", "country", "located_in"]
    a, b = behaviour_of("a", PAINTING_A), behaviour_of("b", PAINTING_B)
    real = distance(a, b, basis)

    def rotate_all(x, off=1):
        return type(x)(x.entity, {basis[(basis.index(k) + off) % len(basis)]: v
                                  for k, v in x.shares.items() if k in basis}, x.edges)
    assert abs(distance(rotate_all(a), rotate_all(b), basis) - real) < 1e-12   # unchanged

    # The real control rotates PER ENTITY, so the alignment the signal lives in is broken. Two
    # entities can still collide onto the same offset -- with a small basis that is common, which is
    # why the gate reads a MEAN over many pairs rather than trusting any single one.
    pool = [behaviour_of(n, [(n, "creator", "X"), (n, "made_of", "c"), (n, "genre", "g")])
            for n in ("p", "q", "r", "s", "t", "u")]
    moved = sum(1 for i in range(len(pool)) for j in range(i + 1, len(pool))
                if abs(distance(shuffled(pool[i], basis), shuffled(pool[j], basis), basis)
                       - distance(pool[i], pool[j], basis)) > 1e-9)
    assert moved > 0


def test_the_gate_needs_the_control_to_fail_not_just_the_effect_to_exist():
    """Without that half, an effect driven by how much an entity is documented reads exactly like
    an effect driven by what it is."""
    groups = {"painting": [behaviour_of("a", PAINTING_A), behaviour_of("b", PAINTING_B)],
              "hill": [behaviour_of("h", HILL_A), behaviour_of("i", HILL_B)]}
    train = [behaviour_of("a", PAINTING_A), behaviour_of("b", PAINTING_B),
             behaviour_of("h", HILL_A), behaviour_of("i", HILL_B)]
    got = read_signal(train, groups)
    assert got.separation > 0
    assert got.passed == (got.separation > got.control_separation * 2)


def test_a_predicate_only_one_entity_holds_is_not_a_dimension():
    """It is that entity's fingerprint, not an axis anything can be compared along."""
    train = [behaviour_of("a", PAINTING_A), behaviour_of("b", PAINTING_B)]
    basis = shared_basis(train)
    assert "genre" in basis and "creator" in basis
    lone = behaviour_of("z", [("z", "manufacturer", "yard")])
    assert "manufacturer" not in shared_basis(train + [lone])
