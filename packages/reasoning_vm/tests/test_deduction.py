# -*- coding: utf-8 -*-
"""Deduction concludes new facts, each with a proof; it never over-concludes."""
from packages.reasoning_vm.deduction import answer_yes_no, deduce


def test_transitivity_with_proof():
    stated = [("서울", "located_in", "대한민국"), ("대한민국", "located_in", "동아시아")]
    res = deduce(stated)
    assert ("서울", "located_in", "동아시아") in res.facts()
    cert = res.certificate(("서울", "located_in", "동아시아"))
    assert cert["rule"].startswith("transitivity") and len(cert["steps"]) == 2


def test_composition_capital_of():
    stated = [("파리", "capital_of", "프랑스"), ("프랑스", "located_in", "유럽")]
    res = deduce(stated)
    assert ("파리", "located_in", "유럽") in res.facts()


def test_type_inheritance():
    stated = [("소크라테스", "is_a", "사람")]
    props = {"사람": [("사람", "is_mortal", "참")]}
    res = deduce(stated, inherit_props=props)
    assert ("소크라테스", "is_mortal", "참") in res.facts()
    assert res.proof_of(("소크라테스", "is_mortal", "참")).rule == "inherit[사람]"


def test_does_not_overconclude():
    # no rule connects these -> nothing derived (honest, not a guess)
    stated = [("고양이", "likes", "생선"), ("개", "likes", "뼈다귀")]
    assert deduce(stated).facts() == set()


def test_answer_yes_no_returns_none_when_unprovable():
    stated = [("A", "is_a", "B")]
    assert answer_yes_no(stated, ("A", "is_a", "Z")) is None      # can't prove -> None
    ok = answer_yes_no([("A", "is_a", "B"), ("B", "is_a", "C")], ("A", "is_a", "C"))
    assert ok["answer"] is True and ok["basis"] == "derived"


def test_bounded_depth_is_sound_and_bounded():
    chain = [(f"n{i}", "is_a", f"n{i+1}") for i in range(10)]
    res = deduce(chain, max_depth=1)
    # SOUND: every derived fact is a genuine transitive pair (i < j), never false
    for (a, _p, b) in res.facts():
        assert int(a[1:]) < int(b[1:])
    # PRODUCTIVE + BOUNDED: near neighbours are derived, but one derivation
    # generation cannot span the whole chain (order-independent bound)
    assert ("n0", "is_a", "n2") in res.facts()
    assert ("n0", "is_a", "n9") not in res.facts()
    assert all(p.depth <= 1 for p in res.derived.values())
