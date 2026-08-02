# -*- coding: utf-8 -*-
"""Perception anchors into the graph geometry — or abstains. Never a silent fact."""
from packages.perceptual_projection.projection import (
    Projection, project_embedding, phase_space_anchors)


def test_clear_anchor_projects_and_is_a_candidate():
    anchors = {"apple": [1.0, 0.0, 0.0], "car": [0.0, 1.0, 0.0], "sky": [0.0, 0.0, 1.0]}
    p = project_embedding([0.95, 0.05, 0.0], anchors, floor=0.55)
    assert p.anchored and p.concept == "apple" and p.confidence > 0.9
    obs = p.as_observation()
    assert obs["status"] == "candidate" and obs["triple"][2] == "apple"


def test_below_floor_abstains():
    anchors = {"apple": [1.0, 0.0], "car": [0.0, 1.0]}
    p = project_embedding([0.71, 0.70], anchors, floor=0.9)   # nothing clears floor
    assert not p.anchored and p.concept is None
    assert p.as_observation() is None                        # never writes a fact


def test_ambiguous_percept_abstains_on_margin():
    anchors = {"apple": [1.0, 0.0], "tomato": [0.99, 0.14]}   # both red & round
    p = project_embedding([0.995, 0.07], anchors, floor=0.5, margin=0.1)
    assert not p.anchored                                     # too close to call -> abstain


def test_phase_space_anchor_table():
    vecs = {"물": [0.1, 0.9], "불": [0.9, 0.1]}
    anchors = phase_space_anchors(["물", "불", "없는개념"], lambda c: vecs.get(c))
    assert set(anchors) == {"물", "불"}                       # missing concept skipped
