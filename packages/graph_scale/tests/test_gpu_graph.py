# -*- coding: utf-8 -*-
"""GPU compute lane: same truths as the CPU lane, device-parallel. Tests run on
whatever device is present (CPU fallback keeps the API identical)."""
import pytest

torch = pytest.importorskip("torch")

from packages.graph_scale.triple_store import TripleStore
from packages.graph_scale.gpu_graph import GpuGraphMirror


def _store(tmp_path, triples):
    st = TripleStore(tmp_path / "s")
    for s, p, o in triples:
        st.add(s, p, o)
    st.flush()
    return st


def test_mirror_uploads_and_refreshes(tmp_path):
    st = _store(tmp_path, [("a", "is_a", "b"), ("b", "is_a", "c")])
    g = GpuGraphMirror(st)
    assert g._rows == 2
    st.add("c", "is_a", "d"); st.flush()
    r = g.refresh()
    assert r["refreshed"] and g._rows == 3


def test_degree_stats_and_noise_mask(tmp_path):
    tris = [("hub", "is_a", f"p{i}") for i in range(12)] + [("cat", "is_a", "mammal")]
    st = _store(tmp_path, tris)
    g = GpuGraphMirror(st)
    d = g.degree_stats("is_a", threshold=8)
    assert d["edges"] == 13
    assert d["noise_magnets"] == 1          # only 'hub' exceeds the threshold
    assert d["max_degree"] == 12


def test_closure_candidates_sound_and_guarded(tmp_path):
    tris = [("cat", "is_a", "mammal"), ("mammal", "is_a", "animal"),
            ("hub", "is_a", "mammal")] + [("hub", "is_a", f"p{i}") for i in range(12)]
    st = _store(tmp_path, tris)
    g = GpuGraphMirror(st)
    r = g.closure_candidates("is_a", max_degree=8)
    pairs = set(g.decode_pairs(r["pairs"], limit=100)) if r["pairs"] is not None else set()
    assert ("cat", "animal") in pairs        # sound 2-hop entailment proposed
    # the hub subject is guarded out — none of its expansions proposed
    assert not any(a == "hub" for a, _ in pairs)


def test_candidates_never_include_stated_or_loops(tmp_path):
    st = _store(tmp_path, [("a", "is_a", "b"), ("b", "is_a", "a"),
                           ("a", "is_a", "c"), ("b", "is_a", "c")])
    g = GpuGraphMirror(st)
    r = g.closure_candidates("is_a", max_degree=8)
    pairs = set(g.decode_pairs(r["pairs"], limit=100)) if r["pairs"] is not None else set()
    assert ("a", "a") not in pairs and ("b", "b") not in pairs   # no loops
    assert ("a", "b") not in pairs and ("a", "c") not in pairs   # no re-stating


def test_empty_relation(tmp_path):
    st = _store(tmp_path, [("a", "alias", "b")])
    g = GpuGraphMirror(st)
    assert g.closure_candidates("is_a")["candidates"] == 0
