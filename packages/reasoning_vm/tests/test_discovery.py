# -*- coding: utf-8 -*-
"""Discovery D0 — deductive closure over transitive relations (entailed edges, un-hallucinatable)."""
from packages.reasoning_vm.discovery import derive_transitive_closure

_KG = {
    "고래": [("고래", "is_a", "포유류")],
    "포유류": [("포유류", "is_a", "동물")],
    "동물": [("동물", "is_a", "생물")],
    "서울": [("서울", "part_of", "대한민국")],
    "대한민국": [("대한민국", "part_of", "아시아"), ("대한민국", "is_a", "국가")],
}


def _fa(s):
    return _KG.get(s, [])


def test_derives_transitive_is_a():
    d = derive_transitive_closure("고래", _fa)
    edges = {(x.subject, x.relation, x.obj) for x in d}
    assert ("고래", "is_a", "동물") in edges
    assert ("고래", "is_a", "생물") in edges


def test_does_not_re_emit_direct_edges():
    d = derive_transitive_closure("고래", _fa)
    edges = {(x.subject, x.relation, x.obj) for x in d}
    assert ("고래", "is_a", "포유류") not in edges  # direct edge is NOT a derivation


def test_part_of_is_transitive_but_not_crossed_with_is_a():
    d = derive_transitive_closure("서울", _fa)
    edges = {(x.subject, x.relation, x.obj) for x in d}
    assert ("서울", "part_of", "아시아") in edges

    assert ("서울", "is_a", "국가") not in edges
    assert ("서울", "part_of", "국가") not in edges


def test_provenance_path_recorded():
    d = derive_transitive_closure("고래", _fa)
    dyn = next(x for x in d if x.obj == "동물")
    assert dyn.path == ["고래", "포유류", "동물"] and dyn.hops == 2


def test_empty_on_unknown_subject():
    assert derive_transitive_closure("없는것", _fa) == []
