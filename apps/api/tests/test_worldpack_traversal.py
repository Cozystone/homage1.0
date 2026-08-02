"""World-pack traversal plumbing: the functional-relation lane must resolve Wikidata Q-id
relation objects ( -capital-> Q90) to readable labels via their 'qlabel' row (Q90 -> ),
so the answer path grounds cleanly against the world pack the moment the full build lands — and
stays byte-identical on the kg_triples store (whose objects are already labels)."""
from __future__ import annotations

import pytest

import packages.graph_scale.answer_bridge as AB
from app.routers import dual_brain
from packages.graph_scale.triple_store import TripleStore


@pytest.fixture(autouse=True)
def _reset_store():
    yield
    AB._STORE["obj"] = None      # clear the pointed store so later tests reload the real one
    AB._STORE["sig"] = None


def _worldpack(tmp_path, monkeypatch):
    """A tiny store in the WORLD-PACK schema: label -relation-> Q-id, Q-id -qlabel-> label."""
    d = tmp_path / "wp"
    st = TripleStore(d, dict_backend="sharded", write_src=False)
    for s, p, o in [
        ("프랑스", "capital", "Q90"), ("Q90", "qlabel", "파리"),
        ("파리", "population", "Q1000"), ("Q1000", "qlabel", "2100000"),
        ("대한민국", "capital", "Q8684"), ("Q8684", "qlabel", "서울특별시"),
    ]:
        st.add(s, p, o)
    st.flush()
    monkeypatch.setattr(AB, "_ROOT", d)
    AB._STORE["obj"] = None
    AB._STORE["sig"] = None


def test_worldpack_qid_resolved_1hop(tmp_path, monkeypatch):
    _worldpack(tmp_path, monkeypatch)
    r = dual_brain._execute_functional_relation("프랑스의 수도는?")
    assert r is not None
    assert "파리" in r["answer"] and "Q90" not in r["answer"]        # Q-id resolved to label
    r2 = dual_brain._execute_functional_relation("대한민국의 수도는?")
    assert r2 is not None and "서울특별시" in r2["answer"] and "Q8684" not in r2["answer"]


def test_worldpack_qid_resolved_2hop(tmp_path, monkeypatch):
    _worldpack(tmp_path, monkeypatch)
    r = dual_brain._execute_functional_relation("프랑스의 수도의 인구는?")
    assert r is not None

    assert "파리" in r["answer"] and "2100000" in r["answer"]
    assert "Q90" not in r["answer"] and "Q1000" not in r["answer"]


def test_kg_triples_label_objects_unchanged(tmp_path, monkeypatch):
    """No-op guarantee (P0): on a store whose objects are already labels (kg_triples shape), the
    resolver changes nothing — the answer is exactly what it was before this surgery."""
    d = tmp_path / "kg"
    st = TripleStore(d, dict_backend="sharded", write_src=False)
    st.add("일본", "capital", "도쿄도")            # label object, no Q-id, no qlabel row
    st.flush()
    monkeypatch.setattr(AB, "_ROOT", d)
    AB._STORE["obj"] = None
    AB._STORE["sig"] = None
    r = dual_brain._execute_functional_relation("일본의 수도는?")
    assert r is not None and "도쿄도" in r["answer"]
