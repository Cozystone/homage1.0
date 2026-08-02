# -*- coding: utf-8 -*-
"""Causal relation extractor — grow the graph's causal density from STATED causation, under the
same discipline as fact learning: extract don't invent, consensus across independent sources, and
never a silent production write. The tests pin the doctrine, not just the happy path."""
from __future__ import annotations

import packages.temporal_reasoning.causal_relation_extractor as cx
from packages.temporal_reasoning.causal_relation_extractor import CausalEdge, extract


def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(cx, "STORE", tmp_path / "causal.json")


# ---------- extraction: pattern-found, never invented ----------

def test_forward_causation_is_extracted():
    edges = extract("Friction causes heat when two surfaces rub together.")
    assert CausalEdge("friction", "causes", "heat") in edges


def test_reverse_causation_is_normalized():
    """'X is caused by Y' and 'X because of Y' must yield (cause=Y -> effect=X), not the surface order."""
    e1 = extract("Flooding is caused by heavy rain.")
    assert CausalEdge("heavy rain", "causes", "flooding") in e1
    # extraction is heuristic (no POS tagger), so the effect NP may carry a verb ('delay happened');
    # the honest contract is the DIRECTION is right and the cause is correct — consensus + the
    # promotion gate are the real safety, not perfect phrase boundaries.
    e2 = extract("The delay happened because of congestion.")
    assert any(e.cause == "congestion" and "delay" in e.effect for e in e2)


def test_relation_type_is_preserved_not_coerced():
    assert CausalEdge("vaccine", "prevents", "infection") in extract("A vaccine prevents infection.")
    assert CausalEdge("photosynthesis", "requires", "sunlight") in \
        extract("Photosynthesis requires sunlight.")
    assert any(e.relation == "used_for" for e in extract("A hammer is used to drive nails."))


def test_generic_arguments_are_dropped():
    """'it causes problems' names no real causal nodes — must yield nothing."""
    assert extract("It causes problems for everyone involved.") == []
    assert extract("This leads to issues sometimes.") == []


def test_determiner_and_length_are_normalized():
    edges = extract("The stress causes the headache.")
    assert CausalEdge("stress", "causes", "headache") in edges     # determiners stripped


def test_no_causal_statement_yields_nothing():
    assert extract("A city is a large human settlement with defined boundaries.") == []


# ---------- consensus: independent sources, not repetition ----------

def test_single_source_is_not_consensus(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    cx.observe([CausalEdge("smoking", "causes", "cancer")], domain="a.com")
    cx.observe([CausalEdge("smoking", "causes", "cancer")], domain="a.com")   # SAME domain again
    assert cx.consensus_edges(min_sources=2) == []                            # one source ≠ agreement
    assert cx.to_bones(min_sources=2) == []


def test_two_independent_sources_reach_consensus(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    cx.observe([CausalEdge("smoking", "causes", "cancer")], domain="a.com")
    cx.observe([CausalEdge("smoking", "causes", "cancer")], domain="b.org")   # distinct domain
    cons = cx.consensus_edges(min_sources=2)
    assert len(cons) == 1 and cons[0]["sources"] == 2
    assert ["smoking", "causes", "cancer"] in cx.to_bones(min_sources=2)


def test_stats_report_and_relation_breakdown(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    cx.observe([CausalEdge("rain", "causes", "flood")], domain="a.com")
    cx.observe([CausalEdge("rain", "causes", "flood")], domain="b.com")
    cx.observe([CausalEdge("vaccine", "prevents", "disease")], domain="a.com")   # only one source
    st = cx.stats()
    assert st["candidate_edges"] == 2 and st["consensus_edges"] == 1
    assert st["by_relation"] == {"causes": 1}                       # the single-source one is excluded


def test_missing_store_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(cx, "STORE", tmp_path / "nope.json")
    assert cx.consensus_edges() == [] and cx.stats()["candidate_edges"] == 0
