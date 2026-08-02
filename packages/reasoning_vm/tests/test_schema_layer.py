# -*- coding: utf-8 -*-
""" L2 — / . : " 
?"→restaurant →" ". SCHEMA (, ) ,
 (>). ."""
from __future__ import annotations

from packages.reasoning_vm.epistemic_memory import EpistemicGraph
from packages.reasoning_vm.schema_layer import SchemaLayer


def _schema():
    s = SchemaLayer()
    s.add("restaurant", triggers=["식당", "레스토랑", "diner"],
          slots={"staff": "웨이터", "payment": "계산대에서 지불", "purpose": "식사"},
          steps=["들어가 자리에 앉는다", "주문한다", "음식을 먹는다", "계산한다", "나간다"])
    s.add("hospital", triggers=["병원", "clinic"],
          slots={"staff": "의사와 간호사", "purpose": "진료"})
    return s


def test_slot_is_typical_schema_grade():
    r = _schema().answer("restaurant", "staff")
    assert r["epistemic_type"] == "SCHEMA" and r["answer"] == "웨이터"
    assert r["surface"] == "보통 웨이터입니다."
    assert 0.5 <= r["confidence"] < 0.85


def test_trigger_word_activates_schema():
    s = _schema()
    assert s.match("식당") == "restaurant"
    assert s.match("레스토랑에서") == "restaurant"
    assert s.match("병원") == "hospital"
    assert s.match("우주정거장") is None


def test_script_returns_ordered_steps():
    steps = _schema().script("restaurant")
    assert steps[0] == "들어가 자리에 앉는다" and steps[-1] == "나간다"
    assert _schema().script("우주정거장") is None


def test_missing_slot_returns_none_not_fabrication():
    assert _schema().answer("restaurant", "정치성향") is None
    assert _schema().answer("우주정거장", "staff") is None




def _brain_with_schema():
    g = EpistemicGraph(schema=_schema())
    g.add_isa("italian_restaurant", "restaurant")
    g.add_fact("italian_restaurant", "purpose", "이탈리아 식사", sources=2)
    return g


def test_fact_beats_schema():
    r = _brain_with_schema().answer("italian_restaurant", "purpose")
    assert r["epistemic_type"] == "KNOWN" and r["answer"] == "이탈리아 식사"


def test_schema_fills_when_no_fact():
    r = _brain_with_schema().answer("restaurant", "staff")
    assert r["epistemic_type"] == "SCHEMA" and r["answer"] == "웨이터"
    assert r["surface"] == "보통 웨이터입니다."


def test_schema_inherited_via_isa_situation():
    r = _brain_with_schema().answer("italian_restaurant", "staff")

    assert r["epistemic_type"] == "SCHEMA" and r["answer"] == "웨이터"


def test_no_schema_still_unknown():
    r = _brain_with_schema().answer("restaurant", "양자스핀")
    assert r["epistemic_type"] == "UNKNOWN"


def test_schema_never_confabulates():
    g = _brain_with_schema()
    for s in ["restaurant", "hospital", "italian_restaurant", "우주정거장"]:
        for p in ["staff", "purpose", "payment", "양자스핀", "정치성향"]:
            assert not g.is_confabulation(g.answer(s, p))
