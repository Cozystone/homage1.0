"""Derived-edge inference: the graph grows from its own structure by DEDUCTION.
Every derived edge must be logically entailed by stated edges + the relation's algebra —
never invented — and the derivation must stay bounded."""
from __future__ import annotations

import tempfile
from pathlib import Path

from packages.graph_scale.inference import derive, derive_into_store
from packages.graph_scale.triple_store import TripleStore


def test_transitive_is_a_chain():
    stated = [("참새", "is_a", "새"), ("새", "is_a", "동물"), ("동물", "is_a", "생물")]
    derived = set(derive(stated))

    assert ("참새", "is_a", "동물") in derived
    assert ("참새", "is_a", "생물") in derived
    assert ("새", "is_a", "생물") in derived
    # never re-emits a stated edge
    assert ("참새", "is_a", "새") not in derived


def test_symmetric_borders():
    derived = set(derive([("프랑스", "borders", "독일")]))
    assert ("독일", "borders", "프랑스") in derived


def test_inverse_capital():
    derived = set(derive([("일본", "capital", "도쿄")]))
    assert ("도쿄", "capital_of", "일본") in derived


def test_subproperty_capital_entails_located_in():
    derived = set(derive([("일본", "capital", "도쿄")]))
    # a capital is located in its country
    assert ("도쿄", "located_in", "일본") in derived


def test_instance_of_is_not_transitive():


    stated = [("소크라테스", "instance_of", "사람"), ("사람", "instance_of", "종")]
    derived = set(derive(stated))
    assert ("소크라테스", "instance_of", "종") not in derived


def test_unknown_relation_yields_nothing():
    # a relation with no declared algebra is safe: no derivations, no fabrication
    assert list(derive([("A", "totally_unknown_rel", "B")])) == []


def test_derive_into_store_multiplies_edges():
    root = Path(tempfile.mkdtemp()) / "kg"
    ts = TripleStore(root)
    ts.bulk_ingest([("참새", "is_a", "새"), ("새", "is_a", "동물"),
                    ("일본", "capital", "도쿄"), ("프랑스", "borders", "독일")])
    before = len(ts)
    r = derive_into_store(ts)
    assert r["derived_added"] > 0
    assert len(ts) == before + r["derived_added"]
    # the entailed skip edge is now stored and queryable
    assert ("참새", "is_a", "동물") in ts.facts_about("참새")
    # reopening keeps the derived edges
    assert ("도쿄", "capital_of", "일본") in TripleStore(root).facts_about("도쿄")
