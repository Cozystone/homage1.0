# -*- coding: utf-8 -*-
"""V7-2: a fitted direction on unseen kinds, and the reasons this could read positive for nothing."""
from __future__ import annotations

from packages.substrate.behaviour import behaviour_of
from packages.substrate.transfer import SEPARATION_GATE, fit_direction, read_transfer, separation

BASIS = ["creator", "made_of", "genre", "country", "located_in", "author"]


def _made(n, tag):
    return behaviour_of(f"{tag}{n}", [(f"{tag}{n}", "creator", f"c{n}"),
                                      (f"{tag}{n}", "made_of", "stuff"),
                                      (f"{tag}{n}", "genre", f"g{n}")])


def _place(n, tag):
    return behaviour_of(f"{tag}{n}", [(f"{tag}{n}", "country", f"C{n}"),
                                      (f"{tag}{n}", "located_in", f"R{n}")])


TRAIN = {"art": [_made(i, "a") for i in range(4)], "town": [_place(i, "t") for i in range(4)]}
HELD = {"game": [_made(i, "g") for i in range(4)], "hill": [_place(i, "h") for i in range(4)]}


def test_the_direction_is_a_subtraction_not_a_trained_fit():
    """Nothing is tuned and there is no objective to overfit. If a subtraction does not carry
    across, nothing heavier was going to."""
    import numpy as np
    d = fit_direction(TRAIN["art"], TRAIN["town"], BASIS)
    assert d is not None and abs(float(np.linalg.norm(d)) - 1.0) < 1e-9


def test_separation_is_direction_agnostic():
    """A direction putting the unseen kinds on the opposite sides still SEPARATES them, and
    separation is the claim."""
    d = fit_direction(TRAIN["art"], TRAIN["town"], BASIS)
    forward = separation(d, HELD["game"], HELD["hill"], BASIS)
    backward = separation(d, HELD["hill"], HELD["game"], BASIS)
    assert abs(forward - backward) < 1e-9 and forward >= 0.5


def test_a_missing_direction_scores_chance_not_zero():
    """An absent direction knows nothing; scoring it 0 would read as evidence against."""
    assert separation(None, HELD["game"], HELD["hill"], BASIS) == 0.5


def test_no_combination_is_selected():
    """Choosing which contrast to fit and which to test on is how a transfer result is
    manufactured. Every fitted pair is scored against every unseen pair."""
    got = read_transfer(TRAIN, HELD, BASIS, control_dirs=4)
    assert got.combinations == got.fitted_pairs * got.tested_pairs


def test_the_control_is_reported_because_random_directions_separate_too():
    """In high dimensions two tight clusters are separated by many directions, so 'some direction
    separates them' is nearly free. Measured on the real graph the control sat at 0.72 against a
    fitted 0.78 -- most of the separation is available for nothing, and a gate that did not report
    the control would have called that a strong result."""
    got = read_transfer(TRAIN, HELD, BASIS, control_dirs=8)
    assert 0.0 <= got.control_mean <= 1.0
    assert got.passed == (got.mean_separation >= SEPARATION_GATE
                          and got.mean_separation > got.control_mean)
