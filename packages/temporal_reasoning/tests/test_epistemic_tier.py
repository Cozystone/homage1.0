# -*- coding: utf-8 -*-
"""Sealed gates for 기관 C — epistemic-tier tagging enforcement.

The two HYPOTHESIS tiers (RETRODICTED / PROJECTED) can never be voiced without their hedge marker, and
a tier tag can never be silently stripped (the claim is immutable). Assertable tiers (PERCEIVED /
RECORDED) pass through untouched.
"""
from __future__ import annotations

import dataclasses

import pytest

from packages.temporal_reasoning.epistemic_tier import (
    EpistemicViolation, Tier, assertable_as_fact, enforce, is_assertable, is_hypothesis, marker_for, tag,
)


def test_hypothesis_and_assertable_partition():
    assert is_hypothesis(Tier.PROJECTED) and is_hypothesis(Tier.RETRODICTED)
    assert not is_hypothesis(Tier.PERCEIVED) and not is_hypothesis(Tier.RECORDED)
    assert is_assertable(Tier.PERCEIVED) and is_assertable(Tier.RECORDED)
    # string tiers normalize identically (no silent mis-tiering)
    assert is_hypothesis("PROJECTED") and is_assertable("RECORDED")


def test_markers_reuse_render_human_phrasing():
    assert marker_for(Tier.PROJECTED) == "a projection, not a certainty"
    assert marker_for(Tier.RETRODICTED) == "an inference from learned order, not a record"
    assert marker_for(Tier.PERCEIVED) is None and marker_for(Tier.RECORDED) is None


def test_enforce_passes_a_properly_hedged_hypothesis():
    fwd = tag("after 'grow', 'harvest' may follow — a projection, not a certainty.", Tier.PROJECTED, 0.7)
    assert enforce(fwd) is fwd
    bwd = tag("'grow' typically precedes 'harvest' — an inference from learned order, not a record.",
              Tier.RETRODICTED, 0.7)
    assert enforce(bwd) is bwd


def test_enforce_refuses_a_stripped_hypothesis_marker():
    # a PROJECTED/RETRODICTED claim voiced as bare certainty must be refused (작화 0)
    for tier in (Tier.PROJECTED, Tier.RETRODICTED):
        bare = tag("The harvest will definitely happen next.", tier, 0.9)
        with pytest.raises(EpistemicViolation):
            enforce(bare)


def test_assertable_tiers_need_no_hedge():
    for tier in (Tier.PERCEIVED, Tier.RECORDED):
        c = tag("the light is on right now.", tier)
        assert enforce(c) is c                       # no raise
        assert assertable_as_fact(c) is True
    # a hypothesis tier is NEVER assertable as fact
    assert assertable_as_fact(tag("... not a certainty.", Tier.PROJECTED)) is False


def test_tier_tag_can_never_be_silently_stripped_or_mutated():
    c = tag("after 'grow', 'harvest' may follow — a projection, not a certainty.", Tier.PROJECTED, 0.7)
    assert c.hypothesis is True and c.assertable is False
    # frozen: you cannot downgrade a projection to a fact, or blank the tier, in place
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.tier = Tier.PERCEIVED
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.text = "the harvest happens."
    # the derived hypothesis flag cannot be constructed out of step with the tier
    assert tag("x", Tier.RETRODICTED).hypothesis is True
    assert tag("x", Tier.RECORDED).hypothesis is False
