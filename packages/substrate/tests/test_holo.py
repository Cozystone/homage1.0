# -*- coding: utf-8 -*-
"""V7-1: the projection into hyperdimensions, and what the control has to be for it to mean anything."""
from __future__ import annotations

from packages.substrate.behaviour import behaviour_of
from packages.substrate.holo import OVERLAP_GATE, holo_distance, project, read_projection

BASIS = ["creator", "made_of", "genre", "country", "located_in", "author"]

PAINTINGS = [behaviour_of(f"p{i}", [(f"p{i}", "creator", f"c{i}"), (f"p{i}", "made_of", "canvas"),
                                    (f"p{i}", "made_of", "oil"), (f"p{i}", "genre", f"g{i}")])
             for i in range(4)]
PLACES = [behaviour_of(f"h{i}", [(f"h{i}", "country", f"C{i}"), (f"h{i}", "located_in", f"R{i}"),
                                 (f"h{i}", "located_in", f"S{i}")])
          for i in range(4)]


def test_the_projection_is_a_superposition_of_the_entitys_own_predicate_atoms():
    """No binding partner is invented and no role vocabulary is authored -- the predicate IS the
    role, which is the occupancy condition fixed before any of this was built."""
    import numpy as np
    v = project(PAINTINGS[0], BASIS)
    assert v is not None and abs(float(np.linalg.norm(v)) - 1.0) < 1e-9


def test_an_entity_with_no_predicate_in_the_basis_projects_to_nothing_not_to_a_default():
    """A default vector would place it somewhere, and somewhere is a claim."""
    stranger = behaviour_of("z", [("z", "manufacturer", "yard")])
    assert project(stranger, BASIS) is None
    assert holo_distance(project(stranger, BASIS), project(PAINTINGS[0], BASIS)) == 1.0


def test_similar_behaviour_lands_nearer_than_different_behaviour():
    a, b = project(PAINTINGS[0], BASIS), project(PAINTINGS[1], BASIS)
    far = project(PLACES[0], BASIS)
    assert holo_distance(a, b) < holo_distance(a, far)


def test_the_control_is_the_current_system_not_an_arbitrary_baseline():
    """Unweighted superposition IS what `fhrr_core` does: an entity as the SET of predicates it has,
    with the distribution over them discarded. If that scores as well, the weights carried nothing
    and moving to hyperdimensions bought nothing."""
    weighted = project(PAINTINGS[0], BASIS, weighted=True)
    plain = project(PAINTINGS[0], BASIS, weighted=False)
    assert holo_distance(weighted, plain) > 0.0        # they are genuinely different points


def test_the_gate_needs_both_the_absolute_bar_and_the_control():
    got = read_projection(PAINTINGS + PLACES, BASIS)
    assert got.gate == OVERLAP_GATE
    assert got.passed == (got.overlap >= OVERLAP_GATE and got.overlap > got.control_overlap)
