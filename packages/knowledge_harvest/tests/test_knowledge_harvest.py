# -*- coding: utf-8 -*-
"""knowledge_harvest: harvester + ingest, and the end-to-end fusion into the base_brain lane.

These run OFFLINE against a TEMP store (never the real 7M-row kg_triples): the harvester's curated
path is deterministic, and the Wikidata parser is exercised on a canned SPARQL response. The load-
bearing assertion is the FUSION: after ingesting into a store, the SAME relational lane resolves
"capital of France" -> Paris with an edge certificate, while an uncovered entity still abstains.
"""
from __future__ import annotations

from packages.knowledge_harvest import RELATION_PIDS, harvest, load_curated
from packages.knowledge_harvest import harvester as H
from packages.knowledge_harvest.ingest import EXCLUDE_PAIRS, ingest_edges
from packages.base_brain.relational_lookup import resolve_relational
from packages.graph_scale.triple_store import TripleStore


# ── harvester (data quality) ─────────────────────────────────────────────────────────────────────
def test_curated_csv_loads_and_is_well_formed():
    edges = load_curated()
    assert len(edges) >= 150, f"curated backbone too small: {len(edges)}"
    for e in edges:
        assert e["subject"] and e["relation"] and e["object"]
        assert e["source"] == "curated"
        assert e["relation"] in RELATION_PIDS, e["relation"]     # only known relation labels


def test_every_edge_carries_a_source_never_fabricated():
    edges, _report = harvest(prefer_live=False)                  # offline curated path
    assert edges
    assert all(e["source"] in ("wikidata", "curated") for e in edges)


def test_curated_excludes_the_test_locked_absences():
    # the two edges the relational-lane regression tests rely on staying ungrounded
    for e in load_curated():
        assert (e["subject"].lower(), e["relation"].lower()) != ("france", "population")
        assert e["subject"].lower() != "water"


def test_wikidata_parser_shapes_edges_from_a_canned_response(monkeypatch):
    canned = [
        {"countryLabel": {"value": "France"}, "capitalLabel": {"value": "Paris"},
         "population": {"value": "68000000"}, "currencyLabel": {"value": "euro"},
         "langLabel": {"value": "French"}, "continentLabel": {"value": "Europe"}},
        {"countryLabel": {"value": "Q1234"},  # unlabelled Q-id must be skipped
         "capitalLabel": {"value": "Nowhere"}},
    ]
    monkeypatch.setattr(H, "_sparql", lambda *a, **k: canned)
    edges = H.fetch_wikidata_countries(limit=10, timeout=1.0)
    rels = {(e["subject"], e["relation"]): e["object"] for e in edges}
    assert rels[("France", "capital")] == "Paris"
    assert rels[("France", "official_language")] == "French"
    assert "68.0 million" == rels[("France", "population")]      # humanized, honest approximation
    assert all(not e["subject"].startswith("Q") for e in edges)  # Q-id row skipped
    assert all(e["source"] == "wikidata" for e in edges)


def test_harvest_reports_which_path_ran():
    _edges, report = harvest(prefer_live=False)
    d = report.as_dict()
    assert d["path"] in ("curated_only", "curated_fallback")
    assert d["curated_edges"] > 0 and d["wikidata_edges"] == 0


# ── the fusion: ingest into a store, the SAME lane now answers ────────────────────────────────────
def _seed_store(tmp_path):
    st = TripleStore(tmp_path)
    # a couple of pre-existing definitional facts, like the real store holds for these entities
    st.add("France", "is_a", "Country")
    st.add("Japan", "is_a", "Country")
    st.add("Hamlet", "defined_as", "A William Shakespeare play about the Danish royal family")
    st.flush()
    return st


def test_ingest_then_lane_answers_capital_of_france_with_certificate(tmp_path):
    st = _seed_store(tmp_path)
    audit = ingest_edges(load_curated(), root=tmp_path)
    assert audit["added"] > 100
    assert audit["single_writer_sanity"]["delta_equals_added"] is True

    st2 = TripleStore(tmp_path)                                  # reopen: reads what ingest wrote
    r = resolve_relational("what is the capital of France?", "en", store=st2)
    assert r is not None and "Paris" in r["answer"]
    assert r["answer_kind"] == "relational_edge_lookup"
    assert r["reasoning_certificate"]["edge"] == "capital"
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False
    assert r["relational"]["resolved"] is True

    # the two other task probes
    pj = resolve_relational("what is the population of Japan?", "en", store=st2)
    assert pj is not None and pj["answer_kind"] == "relational_edge_lookup"
    wh = resolve_relational("who wrote Hamlet?", "en", store=st2)
    assert wh is not None and "Shakespeare" in wh["answer"]


def test_out_of_coverage_entity_still_honestly_abstains(tmp_path):
    _st = _seed_store(tmp_path)
    ingest_edges(load_curated(), root=tmp_path)
    st2 = TripleStore(tmp_path)
    r = resolve_relational("what is the capital of Wakanda?", "en", store=st2)
    assert r is not None
    assert r["answer_kind"] == "honest_abstain_relational"
    assert "don't hold a grounded capital fact for Wakanda" in r["answer"]
    assert r["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False


def test_test_locked_pair_stays_ungrounded_after_ingest(tmp_path):
    _st = _seed_store(tmp_path)
    audit = ingest_edges(load_curated(), root=tmp_path)
    assert audit["excluded_test_locked"] == 0     # curated CSV never contained them (nothing to drop)
    st2 = TripleStore(tmp_path)
    # population of France must NOT be grounded (the lane keeps abstaining, as the regression fixture needs)
    r = resolve_relational("what is the population of France?", "en", store=st2)
    assert r is not None and r["answer_kind"] == "honest_abstain_relational"
    # but population of Japan IS grounded (proves coverage is real, not blanket-abstain)
    j = resolve_relational("what is the population of Japan?", "en", store=st2)
    assert j is not None and j["answer_kind"] == "relational_edge_lookup"


def test_exclude_guard_drops_france_population_even_if_present(tmp_path):
    _st = _seed_store(tmp_path)
    # feed an edge that WOULD ground the test-locked pair (as a live Wikidata pull would) — the guard drops it
    poisoned = load_curated() + [{"subject": "France", "relation": "population",
                                  "object": "68 million", "source": "wikidata"}]
    audit = ingest_edges(poisoned, root=tmp_path)
    assert audit["excluded_test_locked"] == 1
    st2 = TripleStore(tmp_path)
    r = resolve_relational("what is the population of France?", "en", store=st2)
    assert r["answer_kind"] == "honest_abstain_relational"
    assert ("france", "population") in EXCLUDE_PAIRS


def test_ingest_is_idempotent(tmp_path):
    _st = _seed_store(tmp_path)
    a1 = ingest_edges(load_curated(), root=tmp_path)
    a2 = ingest_edges(load_curated(), root=tmp_path)
    assert a1["added"] > 100
    assert a2["added"] == 0                        # everything already present -> no duplication
    assert a2["skipped_already_present"] >= a1["added"]
