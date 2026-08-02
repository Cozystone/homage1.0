# -*- coding: utf-8 -*-
"""Tests for the signal adapters — that each wraps its REAL organ and behaves monotonically."""
from __future__ import annotations

from packages.co_allocator.signals import (
    felt_confidence, x1_voc, difficulty_prior, edge_tree, known_blocks, _NEUTRAL_FELT)


def test_felt_confidence_uncontested_is_high():
    # a single dominant answer with no genuine rival -> high FOR, no conflict
    f = felt_confidence("paris", 1.2, [("city", 0.3), ("europe", 0.2)], grounded=True)
    assert f["for_conf"] >= 0.9
    assert f["conflict"] <= 0.1
    assert f["abstain_margin"] == 0.0


def test_felt_confidence_contested_is_low():
    # a rival within the fraction band -> the felt margin collapses, conflict rises
    f = felt_confidence("paris", 1.0, [("lyon", 0.95)], grounded=True)
    assert f["for_conf"] < 0.5
    assert f["conflict"] > 0.5


def test_felt_confidence_ungrounded_is_gated_down():
    grounded = felt_confidence("x", 1.0, [], grounded=True)["for_conf"]
    guessed = felt_confidence("x", 1.0, [], grounded=False)["for_conf"]
    assert guessed < grounded            # a guessed neighbour is never fully "felt right"


def test_felt_confidence_near_floor_raises_abstain_margin():
    # a winner barely above the abstain floor -> high abstain margin (near abstention)
    f = felt_confidence("x", 0.05, [], grounded=True)
    assert f["abstain_margin"] > 0.5


def test_felt_confidence_is_reproducible_neutral():
    # the probe must NOT read the live body — two calls give the identical number
    a = felt_confidence("paris", 1.0, [("lyon", 0.5)], grounded=True, context=_NEUTRAL_FELT)
    b = felt_confidence("paris", 1.0, [("lyon", 0.5)], grounded=True, context=_NEUTRAL_FELT)
    assert a == b


def test_x1_voc_known_block_is_low_novel_is_high():
    blocks = known_blocks(lambda t: {"france": [("france", "capital", "paris"),
                                                 ("france", "is_a", "country")]}.get(t, []), "france")
    settled = x1_voc(edge_tree("france", "capital", "paris"), blocks)      # an already-known edge
    novel = x1_voc(edge_tree("france", "gdp", "unknownval"), blocks)       # a novel structure
    assert settled < novel
    assert 0.0 <= settled <= 1.0 and 0.0 <= novel <= 1.0


def test_x1_voc_ungrounded_is_max():
    # no answer at all -> maximum VOC (more computation is maximally worth spending)
    assert x1_voc(None, [("ask", ("rel", "x"))]) == 1.0


def test_difficulty_prior_composition_scores_higher():
    easy = difficulty_prior("what is the capital of japan?")
    hard = difficulty_prior("can the ambulance reach the clinic in time AND stay under the weight limit?")
    assert hard > easy
    assert 0.0 <= easy <= 1.0 and 0.0 <= hard <= 1.0
