"""Curated-KG-as-judge: a learned fact that contradicts a curated fact must be quarantined
(the → / is_a class), while facts the curated store confirms or knows
nothing about pass through to the normal consensus gate. Disjointness lives IN the store
(disjoint_with edges), never in code."""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.graph_scale.curated_judge import filter_candidates, judge
from packages.graph_scale.triple_store import TripleStore


def _store(triples):
    ts = TripleStore(Path(tempfile.mkdtemp()) / "kg")
    ts.bulk_ingest(triples)
    return ts


def test_functional_contradiction_quarantined():
    ts = _store([("일본", "capital", "도쿄도")])
    v = judge("일본", "capital", "오사카", ts)
    assert v["verdict"] == "contradicted"
    assert "일본 capital 도쿄도" in v["evidence"]


def test_consistent_and_unknown():
    ts = _store([("일본", "capital", "도쿄도")])
    assert judge("일본", "capital", "도쿄도", ts)["verdict"] == "consistent"
    assert judge("퀴리", "discovered", "라듐", ts)["verdict"] == "unknown"  # no evidence -> consensus gate decides


def test_non_functional_predicate_never_contradicts():
    # a person can discover MANY things; a second object is not a contradiction
    ts = _store([("퀴리", "discovered", "라듐")])
    assert judge("퀴리", "discovered", "폴로늄", ts)["verdict"] == "unknown"


def test_type_conflict_via_disjoint_with_edges():


    ts = _store([("중력", "is_a", "상호작용"), ("상호작용", "disjoint_with", "이론")])
    v = judge("중력", "is_a", "이론", ts)
    assert v["verdict"] == "type_conflict"


def test_filter_candidates_splits():
    ts = _store([("일본", "capital", "도쿄도")])
    r = filter_candidates([("일본", "capital", "오사카"), ("한국", "capital", "서울")], ts)
    assert r["promotable"] == [("한국", "capital", "서울")]
    assert len(r["quarantined"]) == 1 and r["quarantined"][0]["fact"] == ("일본", "capital", "오사카")


def test_abstain_queue_roundtrip(tmp_path, monkeypatch):
    from packages.graph_scale import abstain_queue as aq

    monkeypatch.setattr(aq, "QUEUE_PATH", tmp_path / "q.jsonl")
    # English-only (owner 2026-07-18): the Korean original was retired with the Kiwi lane; the
    # queue behaviour under test — record, transition, no duplicate — is unchanged.
    added = aq.record_abstain("Where is Seongnam?")
    assert "Seongnam" in added
    assert "Seongnam" in aq.pending()
    aq.mark("Seongnam", "ingested", "2 facts")
    assert "Seongnam" not in aq.pending()        # status transition consumed it
    # re-recording the same term does not duplicate
    assert aq.record_abstain("Tell me about Seongnam") == []
