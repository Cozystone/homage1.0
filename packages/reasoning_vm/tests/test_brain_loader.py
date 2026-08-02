# -*- coding: utf-8 -*-
""" — →(,) (//) ( ).
 ( 1 ), None."""
from __future__ import annotations

from pathlib import Path

import pytest

from packages.reasoning_vm.brain_loader import parse_question, CAND


def test_parse_english_forms():
    assert parse_question("what can a dog do?") == ("dog", "capable_of")
    assert parse_question("what is a car used for") == ("car", "used_for")
    assert parse_question("what causes rain") == ("rain", "원인")
    assert parse_question("where is paris") == ("paris", "located_in")
    assert parse_question("properties of water") == ("water", "has_property")


def test_parse_korean_forms():
    assert parse_question("강아지는 무엇을 할 수 있어") == ("강아지", "capable_of")
    assert parse_question("파리는 어디에 있어") == ("파리", "located_in")


def test_parse_explicit_forms():
    assert parse_question("penguin|capable_of") == ("penguin", "capable_of")   # s|p
    assert parse_question("dog.capable_of") == ("dog", "capable_of")           # s.p


def test_parse_unparseable_is_none_not_fabricated():
    assert parse_question("음 그냥 아무말이나 해볼게 오늘 날씨가") is None
    assert parse_question("hello there friend") is None


def test_parse_verify_questions():
    from packages.reasoning_vm.brain_loader import parse_verify_question
    assert parse_verify_question("can a penguin fly?") == ("penguin", "capable_of", "fly")
    assert parse_verify_question("is a whale a mammal?") == ("whale", "is_a", "mammal")
    assert parse_verify_question("고래는 포유류야?") == ("고래", "is_a", "포유류")
    assert parse_verify_question("penguin|capable_of|fly") == ("penguin", "capable_of", "fly")
    assert parse_verify_question("그냥 잡담이야 오늘") is None


def test_seeded_schema_answers_typical():
    from packages.reasoning_vm.schema_layer import SchemaLayer
    from packages.reasoning_vm.brain_loader import _seed_schemas
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    sch = SchemaLayer(); _seed_schemas(sch)
    g = EpistemicGraph(schema=sch)
    r = g.answer("식당", "staff")
    assert r["epistemic_type"] == "SCHEMA" and r["answer"] == "웨이터"


@pytest.mark.skipif(not (CAND / "conceptnet_is_a.jsonl").exists(), reason="파생 후보 데이터 없음")
def test_real_brain_grades_honestly_no_confab():
    from packages.reasoning_vm.brain_loader import load_real_brain
    g = load_real_brain(max_isa=50000, max_facts=8000, with_store=False)
    assert g._load_stats["is_a_edges"] > 1000 and g._load_stats["facts"] > 1000

    confab = 0
    for s, p in [("paris", "located_in"), ("car", "used_for"), ("penguin", "capable_of"),
                 ("존재하지않는것xyz", "capable_of")]:
        r = g.answer(s, p)
        assert r["epistemic_type"] in {"KNOWN", "INHERITED", "SCHEMA", "ANALOGIZED", "GUESSED", "UNKNOWN"}
        confab += int(g.is_confabulation(r))
    assert confab == 0
    assert g.answer("존재하지않는것xyz", "capable_of")["epistemic_type"] == "UNKNOWN"


def test_store_lookup_direct_fact_takes_priority():

    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    def fake_store(s, p):
        return {("커피", "defined_as"): ["커피나무 열매로 만든 음료"]}.get((s, p))
    g = EpistemicGraph(store_lookup=fake_store)
    r = g.answer("커피", "defined_as")
    assert r["epistemic_type"] == "KNOWN" and r["answer"] == "커피나무 열매로 만든 음료"
    assert g.answer("없는것", "defined_as")["epistemic_type"] == "UNKNOWN"


@pytest.mark.skipif(not (REPO_KG := (CAND.parents[1] / "graph_scale" / "kg_triples" / "meta.json")).exists(),
                    reason="kg_triples 스토어 없음")
def test_real_store_answers_english_definition():
    """Post the English-only rebuild (english-only-enforcement / english-rebuild-surgery), the
 store answers ENGLISH definitions; Korean definition edges were removed BY DESIGN, so a Korean
 lookup is honestly UNKNOWN — the architecture, not a gap. (Was 'korean_definition' asserting
 →KNOWN; measured 2026-07-18: // UNKNOWN, coffee/water/Germany KNOWN.)"""
    from packages.reasoning_vm.brain_loader import load_real_brain
    g = load_real_brain(max_isa=20000, max_facts=4000, with_store=True)
    if "unavailable" in str(g._load_stats.get("store", "")):
        import pytest as _pt; _pt.skip("스토어 열기 실패")
    r = g.answer("coffee", "defined_as")                                          # on-demand 7.17M
    assert r["epistemic_type"] == "KNOWN" and r["answer"]                          # real definition
    assert not g.is_confabulation(r)
    assert g.answer("커피", "defined_as")["epistemic_type"] == "UNKNOWN"           # KO removed by design
