# -*- coding: utf-8 -*-
"""The derivation accelerator must add ONLY sound, genuinely-new edges."""
import numpy as np
import pytest

from packages.graph_scale.triple_store import TripleStore
from packages.graph_scale.derivation_accelerator import accelerate


def _store(tmp_path, triples):
    st = TripleStore(tmp_path / "s")
    for s, p, o in triples:
        st.add(s, p, o)
    st.flush()
    return st


def test_two_hop_transitive_closure(tmp_path):
    # cat ⊂ mammal ⊂ animal  ⟹  cat ⊂ animal (new, sound)
    st = _store(tmp_path, [("cat", "is_a", "mammal"), ("mammal", "is_a", "animal")])
    res = accelerate(st, max_new=100)
    facts = {(s, o) for s, p, o in _all(st) if p == "is_a"}
    assert ("cat", "animal") in facts        # the entailed edge is materialised
    assert res["derived"] >= 1


def test_no_self_loops(tmp_path):
    # a cycle must not emit A⊂A
    st = _store(tmp_path, [("a", "is_a", "b"), ("b", "is_a", "a")])
    accelerate(st, max_new=100)
    facts = {(s, o) for s, p, o in _all(st) if p == "is_a"}
    assert ("a", "a") not in facts and ("b", "b") not in facts


def test_never_restates_existing(tmp_path):
    # cat⊂animal already stated directly — the closure must not re-add it (count it new)
    st = _store(tmp_path, [("cat", "is_a", "mammal"), ("mammal", "is_a", "animal"),
                           ("cat", "is_a", "animal")])
    before = len(st)
    res = accelerate(st, max_new=100)
    # only genuinely-new edges counted; cat⊂animal was already there
    assert len(st) == before + res["derived"]


def test_inverse_edges(tmp_path):
    st = _store(tmp_path, [("Korea", "capital", "Seoul")])
    accelerate(st, max_new=100)
    facts = {(s, p, o) for s, p, o in _all(st)}
    assert ("Seoul", "capital_of", "Korea") in facts


def test_derived_edges_are_source_tagged(tmp_path):
    st = _store(tmp_path, [("cat", "is_a", "mammal"), ("mammal", "is_a", "animal")])
    accelerate(st, max_new=100)
    # a `derived:*` source was interned (provenance-honest: derived != web-verified)
    assert (tmp_path / "s" / "sources.txt").read_text(encoding="utf-8").count("derived:") >= 1


def test_bounded_and_resumable(tmp_path):
    tris = [(f"c{i}", "is_a", f"m{i%50}") for i in range(500)]
    tris += [(f"m{i}", "is_a", "root") for i in range(50)]
    st = _store(tmp_path, tris)
    res = accelerate(st, max_new=100, edge_window=100, cursor=0)
    assert res["derived"] <= 100                 # respects the cap
    assert "next_cursor" in res and res["edges_scanned"] <= 100


def test_empty_store(tmp_path):
    st = TripleStore(tmp_path / "s")
    res = accelerate(st, max_new=100)
    assert res["derived"] == 0


def _all(st):
    cols = st.open_columns()
    return [(st.terms.term(int(cols["s"][i])), st.terms.term(int(cols["p"][i])),
             st.terms.term(int(cols["o"][i]))) for i in range(len(cols["s"]))]
