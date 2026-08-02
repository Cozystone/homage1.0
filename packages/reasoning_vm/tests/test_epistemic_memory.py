# -*- coding: utf-8 -*-
""" — : =KNOWN·=INHERITED· ·
=GUESSED/UNKNOWN. (>1>>) ."""
from __future__ import annotations

from packages.reasoning_vm.epistemic_memory import EpistemicGraph


def _brain():
    g = EpistemicGraph()
    g.add_isa("penguin", "bird"); g.add_isa("robin", "bird")
    g.add_isa("bird", "animal"); g.add_isa("animal", "living_thing")
    g.add_fact("bird", "reproduction", "lays_eggs", sources=3)
    g.add_fact("bird", "can_fly", "yes", sources=3)
    g.add_fact("animal", "needs", "energy", sources=4)
    g.add_override("penguin", "can_fly", "no", sources=3)
    g.add_prior("favorite_color", "unknown_color", 0.3)
    return g


def test_direct_is_known():
    r = _brain().answer("bird", "can_fly")
    assert r["epistemic_type"] == "KNOWN" and r["answer"] == "yes"
    assert r["confidence"] >= 0.85 and r["surface"] == "yes입니다."


def test_inheritance_is_probable_not_certain():
    r = _brain().answer("penguin", "reproduction")
    assert r["epistemic_type"] == "INHERITED" and r["answer"] == "lays_eggs"
    assert "일반적으로" in r["surface"]
    assert r["confidence"] < _brain().answer("bird", "reproduction")["confidence"]


def test_override_beats_inheritance():
    r = _brain().answer("penguin", "can_fly")
    assert r["epistemic_type"] == "KNOWN" and r["answer"] == "no"


def test_deeper_inheritance_lower_confidence():
    g = _brain()
    near = g.answer("bird", "needs")
    far = g.answer("penguin", "needs")
    assert near["epistemic_type"] == far["epistemic_type"] == "INHERITED"
    assert far["confidence"] < near["confidence"]


def test_no_basis_is_guess_or_unknown():
    g = _brain()
    guess = g.answer("penguin", "favorite_color")
    assert guess["epistemic_type"] == "GUESSED" and "확실치 않지만" in guess["surface"]
    unk = g.answer("penguin", "quantum_spin")
    assert unk["epistemic_type"] == "UNKNOWN" and unk["surface"] == "그건 잘 모르겠습니다."


def test_no_confabulation_invariant():
    g = _brain()
    for s in ["penguin", "bird", "robin"]:
        for p in ["can_fly", "reproduction", "needs", "favorite_color", "quantum_spin"]:
            assert not g.is_confabulation(g.answer(s, p))




def test_verify_isa_affirms_along_chain():
    g = EpistemicGraph()
    g.add_isa("whale", "mammal"); g.add_isa("mammal", "animal")
    assert g.verify("whale", "is_a", "mammal")["verdict"] == "AFFIRM"
    assert g.verify("whale", "is_a", "animal")["verdict"] == "AFFIRM"
    assert g.verify("whale", "is_a", "animal")["confidence"] < \
           g.verify("whale", "is_a", "mammal")["confidence"]


def test_verify_override_refutes():
    r = _brain().verify("penguin", "can_fly", "yes")
    assert r["verdict"] == "REFUTE" and "아니" in r["surface"]


def test_verify_absence_is_unconfirmed_not_false_no():
    g = EpistemicGraph()
    g.add_fact("dog", "capable_of", "bark", sources=4)
    r = g.verify("dog", "capable_of", "fly")
    assert r["verdict"] == "UNCONFIRMED" and r.get("known_value") == "bark"
    assert g.verify("whale", "is_a", "plant")["verdict"] == "UNCONFIRMED"


def test_verify_total_unknown():
    assert _brain().verify("cat", "capable_of", "meow")["verdict"] == "UNKNOWN"


def test_explain_narrates_inheritance_chain():
    r = _brain().explain("penguin", "reproduction")
    assert r["epistemic_type"] == "INHERITED"
    assert "bird" in r["why"] and "일종" in r["why"]
    assert "확실치는 않습니다" in r["why"]
    assert _brain().explain("bird", "reproduction")["why"].startswith("'bird'에 대해 직접")
    assert "근거가 없어" in _brain().explain("penguin", "mystery_x")["why"]
