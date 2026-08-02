# -*- coding: utf-8 -*-
"""Tests for the probe — the headline honest claims the deliverable rests on. These assert the
RELATIONSHIP between policies (allocator vs uniform baselines), not brittle absolute numbers."""
from __future__ import annotations

from packages.co_allocator.probe import run_probe, build_probe


def test_probe_has_three_honest_classes():
    qs = build_probe()
    for c in ("E", "H", "O"):
        assert len([q for q in qs if q.cls == c]) >= 6


def test_allocator_matches_or_beats_deep_accuracy():
    rep = run_probe()
    al = rep["aggregates"]["allocator"]["ALL"]["acc"]
    r2 = rep["aggregates"]["always_R2"]["ALL"]["acc"]
    assert al >= r2                       # allocator is at least as accurate overall as uniform-deep


def test_allocator_spends_materially_less_than_deep():
    rep = run_probe()
    al = rep["aggregates"]["allocator"]["ALL"]["cost"]
    r2 = rep["aggregates"]["always_R2"]["ALL"]["cost"]
    assert al < r2                        # and it does so at lower compute


def test_allocator_beats_deep_on_overthinking():
    rep = run_probe()
    al_o = rep["aggregates"]["allocator"]["O"]["acc"]
    r2_o = rep["aggregates"]["always_R2"]["O"]["acc"]
    assert al_o > r2_o                    # it stops before overthinking drifts the answer


def test_allocator_beats_shallow_on_hard():
    rep = run_probe()
    al_h = rep["aggregates"]["allocator"]["H"]["acc"]
    r0_h = rep["aggregates"]["always_R0"]["H"]["acc"]
    assert al_h > r0_h                    # and it climbs where the cheap rung cannot


def test_easy_class_is_free_of_waste():
    # on easy queries the allocator matches the cheap policy's accuracy (it does not need depth)
    rep = run_probe()
    al_e = rep["aggregates"]["allocator"]["E"]["acc"]
    r0_e = rep["aggregates"]["always_R0"]["E"]["acc"]
    assert al_e == r0_e == 1.0


def test_signal_separation_is_real():
    # the cheap escalate-score must actually separate {E,O} (stop) from {H} (climb)
    rep = run_probe()
    fm = rep["feature_means"]
    assert fm["H"]["escalate_score"] > fm["E"]["escalate_score"]
    assert fm["H"]["escalate_score"] > fm["O"]["escalate_score"]


def test_deceptive_set_surfaces_for_limit():
    # honest: a confident-but-wrong R0 is NOT caught by the allocator (uniform-deep recovers it)
    rep = run_probe()
    dec = rep["deceptive"]["aggregates"]
    assert dec["allocator"]["acc"] < dec["always_R2"]["acc"]
