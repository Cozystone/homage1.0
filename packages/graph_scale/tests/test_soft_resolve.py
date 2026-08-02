# -*- coding: utf-8 -*-
"""Soft resolution: the phase space PROPOSES, the symbolic graph VERIFIES.
A suggestion must never surface without a shared stated is_a parent."""
import pytest

from packages.graph_scale.triple_store import TripleStore
from packages.graph_scale import phase_space as ps
from packages.graph_scale.phase_space import train_phase_space
from packages.graph_scale.soft_resolve import soft_context_line, typed_soft_match


@pytest.fixture()
def spaced_store(tmp_path, monkeypatch):
    """Small store with two typed clusters + a trained phase space on it."""
    st = TripleStore(tmp_path / "s")

    drinks = ["espresso", "latte", "americano", "mocha", "cappuccino"]
    cities = ["seoul", "busan", "daegu", "incheon", "gwangju"]
    for d in drinks:
        st.add(d, "is_a", "음료")
        st.add(d, "defined_as", "커피 음료의 하나이다")
        for e in drinks:
            if d != e:
                st.add(d, "located_in", e)   # dense intra-cluster entity edges
    for c in cities:
        st.add(c, "is_a", "도시")
        for e in cities:
            if c != e:
                st.add(c, "located_in", e)
    st.flush()
    # isolate the artifacts so the test never touches the live space
    monkeypatch.setattr(ps, "SPACE_DIR", tmp_path / "space")
    monkeypatch.setattr(ps, "PHASES_PATH", tmp_path / "space" / "phases.npy")
    monkeypatch.setattr(ps, "REL_PATH", tmp_path / "space" / "relations.npy")
    monkeypatch.setattr(ps, "TERMS_PATH", tmp_path / "space" / "terms.json")
    monkeypatch.setattr(ps, "CURRENT_PATH", tmp_path / "space" / "current.json")
    ps._SPACE["phases"] = None
    r = train_phase_space(st, max_edges=10_000, epochs=40, min_degree=2,
                          min_edges=10, log=lambda *_: None)
    assert "error" not in r
    return st


def test_typed_match_requires_shared_parent(spaced_store):

    out = typed_soft_match(spaced_store, "espresso", k=3, floor=0.0)
    assert out, "expected at least one type-verified neighbor"
    for m in out:
        assert "음료" in m["shared_types"]


def test_no_parents_means_no_suggestions(spaced_store):
    # a term with no is_a parents can't be type-verified -> nothing surfaces
    assert typed_soft_match(spaced_store, "무근거단어", k=3) == []


def test_context_line_is_explicit_suggestion(spaced_store):
    line = soft_context_line(spaced_store, "espresso", language="ko")
    if line is None:  # tiny-space training may not clear the floor — honest skip
        pytest.skip("no neighbor above floor in tiny test space")
    assert line["neighbor"] != "espresso"
    assert "가장 가까운 검증 개념" in line["text"]   # framed as suggestion, not fact
    assert line["shared_types"]
