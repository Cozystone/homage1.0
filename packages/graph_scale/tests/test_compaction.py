# -*- coding: utf-8 -*-
"""Knowledge compaction (self-refine stage 2) — merge surface forms, keep meaning."""

from __future__ import annotations

import packages.graph_scale.compaction as cp
from packages.cloud_brain.alias_resolution import AliasResolver
from packages.graph_scale.triple_store import TripleStore


def _store(tmp_path):
    st = TripleStore(tmp_path / "kg")
    # the same entity under three surface forms + a distinct entity
    st.add("엔비디아", "is_a", "반도체 기업")
    st.add("Nvidia", "설립자", "젠슨 황")
    st.add("엔비디아 코퍼레이션", "본사", "산타클라라")
    st.add("바다", "defined_as", "소금물이 넓게 고인 곳")  # unrelated, must survive
    st.flush()
    return st


def test_no_aliases_means_no_compaction(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "LEDGER", tmp_path / "cl.jsonl")
    st = _store(tmp_path)
    resolver = AliasResolver()  # empty — knows no aliases
    out = cp.compact(st, resolver, apply=True)
    assert out["rewritten"] == 0 and out["nodes_merged"] == 0  # never guesses


def test_learned_aliases_merge_to_canonical(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "LEDGER", tmp_path / "cl.jsonl")
    st = _store(tmp_path)
    resolver = AliasResolver()
    resolver.add_pair("엔비디아", "Nvidia", persist=False)
    resolver.add_pair("엔비디아", "엔비디아 코퍼레이션", persist=False)

    out = cp.compact(st, resolver, apply=True)
    assert out["nodes_merged"] == 2   # two variants folded into the canonical
    assert out["rewritten"] >= 2
    # all three facts now live under one canonical form (Korean, most-used)
    canon = "엔비디아"
    facts = st.facts_about(canon, limit=10)
    preds = {p for (_s, p, _o) in facts}
    assert {"is_a", "설립자", "본사"} <= preds
    # the variant nodes no longer hold their own facts
    assert st.facts_about("Nvidia", limit=5) == []
    # the unrelated entity is untouched
    assert st.facts_about("바다", limit=5) == [("바다", "defined_as", "소금물이 넓게 고인 곳")]


def test_compaction_defaults_to_observe_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "LEDGER", tmp_path / "cl.jsonl")
    st = _store(tmp_path)
    resolver = AliasResolver()
    resolver.add_pair("엔비디아", "Nvidia", persist=False)
    before = list(st.facts_about("Nvidia", limit=5))

    out = cp.compact(st, resolver)

    assert out["nodes_merged"] == 1
    assert out["rewritten"] == 0
    assert st.facts_about("Nvidia", limit=5) == before
    assert not (st.root / "retractions.jsonl").exists()


def test_canonical_prefers_most_referenced_then_korean(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "LEDGER", tmp_path / "cl.jsonl")
    st = TripleStore(tmp_path / "kg")

    st.add("GPU", "is_a", "장치")
    st.add("GPU", "용도", "그래픽")
    st.add("GPU", "제조", "엔비디아")
    st.add("지피유", "별칭", "그래픽카드")
    st.flush()
    resolver = AliasResolver()
    resolver.add_pair("GPU", "지피유", persist=False)
    cp.compact(st, resolver, apply=True)
    # GPU is referenced far more -> it wins as canonical
    assert len(st.facts_about("GPU", limit=10)) >= 4
    assert st.facts_about("지피유", limit=5) == []
