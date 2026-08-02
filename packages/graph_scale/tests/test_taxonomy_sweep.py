# -*- coding: utf-8 -*-
"""Taxonomic-noise sweep — structurally impossible is_a edges are pure noise."""

from __future__ import annotations

import packages.graph_scale.contradiction_sweep as cs
from packages.graph_scale.triple_store import TripleStore


def test_self_loop_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "l.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("고양이", "is_a", "고양이")           # X is_a X — impossible
    st.add("고양이", "is_a", "포유류")           # legit, must survive
    st.flush()
    out = cs.sweep_taxonomy(st, apply=True)
    assert out["removed"] == 1
    facts = st.facts_about("고양이", limit=10)
    assert ("고양이", "is_a", "포유류") in facts
    assert ("고양이", "is_a", "고양이") not in facts


def test_taxonomy_sweep_defaults_to_observe_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "l.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("고양이", "is_a", "고양이")
    st.flush()

    out = cs.sweep_taxonomy(st)

    assert out == {"taxonomic_noise": 1, "removed": 0}
    assert ("고양이", "is_a", "고양이") in st.facts_about("고양이", limit=10)
    assert not (st.root / "retractions.jsonl").exists()


def test_mutual_is_a_drops_thinner_node(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "l.jsonl")
    st = TripleStore(tmp_path / "kg")


    st.add("어버이", "is_a", "아버지")   # backwards (noise)
    st.add("아버지", "is_a", "어버이")   # correct direction
    st.add("어버이", "defined_as", "부모")
    st.add("어버이", "관련", "가족")
    st.flush()
    out = cs.sweep_taxonomy(st, apply=True)
    assert out["taxonomic_noise"] >= 1 and out["removed"] == 1
    # exactly one direction survives (no mutual loop remains)
    a = [f for f in st.facts_about("어버이", limit=20) if f[1] == "is_a"]
    b = [f for f in st.facts_about("아버지", limit=20) if f[1] == "is_a"]
    assert len(a) + len(b) == 1


def test_clean_taxonomy_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "l.jsonl")
    st = TripleStore(tmp_path / "kg")
    st.add("참새", "is_a", "새")
    st.add("새", "is_a", "동물")
    st.flush()
    out = cs.sweep_taxonomy(st, apply=True)
    assert out["taxonomic_noise"] == 0 and out["removed"] == 0
    assert ("참새", "is_a", "새") in st.facts_about("참새", limit=5)
