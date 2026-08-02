"""Predicate algebra: fixed operators in code, predicate properties as data."""
from __future__ import annotations

from cgsr.predicate_algebra import PredicateProperties, induce_properties, infer


def test_transitive_closure_with_trace():
    props = PredicateProperties(transitive={"IS_A"})
    facts = [("진돗개", "IS_A", "개"), ("개", "IS_A", "포유류"), ("포유류", "IS_A", "동물")]
    res = infer(facts, props)
    assert ("진돗개", "IS_A", "포유류") in res.facts()
    assert ("진돗개", "IS_A", "동물") in res.facts()
    depth2 = next(d for d in res.derived if d.fact == ("진돗개", "IS_A", "동물"))
    assert len(depth2.trace) == 3  # full derivation path, XAI-ready
    assert depth2.operator == "transitive_closure"


def test_symmetry_and_inverse():
    props = PredicateProperties(symmetric={"인접하다"}, inverse={"PART_OF": "HAS_PART"})
    facts = [("한국", "인접하다", "북한"), ("엔진", "PART_OF", "자동차")]
    res = infer(facts, props)
    assert ("북한", "인접하다", "한국") in res.facts()
    assert ("자동차", "HAS_PART", "엔진") in res.facts()


def test_isa_inheritance_of_inheritable_predicates():
    props = PredicateProperties(inheritable={"CAN"})
    facts = [("참새", "IS_A", "새"), ("새", "CAN", "비행")]
    res = infer(facts, props)
    assert ("참새", "CAN", "비행") in res.facts()
    d = next(x for x in res.derived if x.fact == ("참새", "CAN", "비행"))
    assert d.operator == "isa_inheritance" and len(d.trace) == 2


def test_functional_conflict_is_exposed_not_inferred():
    props = PredicateProperties(functional={"수도"})
    facts = [("한국", "수도", "서울"), ("한국", "수도", "부산")]
    res = infer(facts, props)
    assert len(res.conflicts) == 1
    assert res.conflicts[0]["objects"] == ["부산", "서울"]
    assert res.conflicts[0]["resolution"] == "exclusion_group -> truth_discovery"


def test_properties_induced_from_observed_data():

    facts = []
    for a, b in [("A", "B"), ("B", "A"), ("C", "D"), ("D", "C"), ("E", "F"), ("F", "E")]:
        facts.append((a, "맞닿다", b))
    for s, o in [("한국", "서울"), ("일본", "도쿄"), ("프랑스", "파리")]:
        facts.append((s, "수도", o))
    props = induce_properties(facts)
    assert "맞닿다" in props.symmetric
    assert "수도" in props.functional
    assert "맞닿다" not in props.functional  # both-direction pairs are not 1:1


def test_bounded_inference_never_explodes():
    props = PredicateProperties(transitive={"IS_A"})
    chain = [(f"n{i}", "IS_A", f"n{i+1}") for i in range(200)]
    res = infer(chain, props, max_depth=3, max_derived=50)
    assert len(res.derived) <= 50
    assert res.truncated


def test_lexicon_file_loads():
    props = PredicateProperties.load()
    assert "IS_A" in props.transitive
    assert props.inverse.get("PART_OF") == "HAS_PART"
