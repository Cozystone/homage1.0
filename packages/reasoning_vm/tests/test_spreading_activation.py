# -*- coding: utf-8 -*-
""" L3 — + . (··top-k ), EpistemicGraph :
·· ANALOGIZED(" ")
. — KNOWN . (UNKNOWN)."""
from __future__ import annotations

from packages.reasoning_vm.epistemic_memory import EpistemicGraph
from packages.reasoning_vm.spreading_activation import SpreadingActivation


def test_activation_spreads_and_decays():
    sa = SpreadingActivation(decay=0.5, threshold=0.01)
    sa.add_edge("a", "b"); sa.add_edge("b", "c")
    energy = sa.activate("a", max_steps=3)
    assert energy["b"] > energy["c"] > 0
    assert "a" not in energy


def test_related_ranks_coactivation():
    sa = SpreadingActivation()
    sa.add_edge("dog", "animal"); sa.add_edge("cat", "animal"); sa.add_edge("car", "vehicle")
    rel = dict(sa.related("dog", k=5))
    assert "animal" in rel
    assert rel.get("cat", 0) > rel.get("car", 0)


def _assoc_brain():
    g = EpistemicGraph()
    g.add_fact("coffee", "contains", "caffeine", sources=3)
    g.add_fact("tea", "contains", "caffeine", sources=3)
    g.add_fact("tea", "effect", "alertness", sources=2)
    return g


def test_analogized_fills_gap_marked_weak():
    r = _assoc_brain().answer("coffee", "effect")
    assert r["epistemic_type"] == "ANALOGIZED" and r["answer"] == "alertness"
    assert "미루어" in r["surface"]
    assert r["confidence"] <= 0.5


def test_analogize_never_upgrades_to_known():
    g = _assoc_brain()
    r = g.answer("coffee", "effect")
    assert r["epistemic_type"] != "KNOWN"
    assert not g.is_confabulation(r)


def test_no_activation_path_is_unknown():
    g = _assoc_brain()
    r = g.answer("granite", "effect")
    assert r["epistemic_type"] == "UNKNOWN"


def test_fact_and_inheritance_beat_analogy():
    g = _assoc_brain()
    g.add_fact("coffee", "effect", "energy_boost", sources=2)
    r = g.answer("coffee", "effect")
    assert r["epistemic_type"] == "KNOWN" and r["answer"] == "energy_boost"


def test_spreading_off_falls_through_to_unknown():
    g = EpistemicGraph(spreading=False)
    g.add_fact("coffee", "contains", "caffeine"); g.add_fact("tea", "contains", "caffeine")
    g.add_fact("tea", "effect", "alertness")
    assert g.answer("coffee", "effect")["epistemic_type"] == "UNKNOWN"
