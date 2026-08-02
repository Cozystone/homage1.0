"""Autonomous Creative XAI: graph-native creation (blend/break), grounded + explained, no rules."""
from __future__ import annotations

import json
import pathlib

import pytest

from cgsr.creative_engine import CreativeEngine

CURATED = [
    ("전화", "USED_FOR", "통신"), ("전화", "IS_A", "기기"),
    ("카메라", "USED_FOR", "촬영"), ("카메라", "IS_A", "기기"),
    ("자동차", "IS_A", "탈것"), ("자동차", "USED_FOR", "이동"),
    ("감자", "IS_A", "채소"), ("감자", "USED_FOR", "식용"),
    ("교육", "HAPPENS_AT", "학교"), ("교육", "USED_FOR", "학습"),
    ("은행", "HAPPENS_AT", "건물"), ("상점", "HAPPENS_AT", "건물"),
]


def test_blend_ranks_coherent_over_random():


    e = CreativeEngine(CURATED)
    good = e.blend("전화", "카메라")
    junk = e.blend("자동차", "감자")
    assert good.creative_score > junk.creative_score
    assert junk.scores["consistency"] == 0.0  # disjoint types → incoherent


def test_creation_is_grounded_in_real_triples():
    e = CreativeEngine(CURATED)
    c = e.blend("전화", "카메라")
    assert ("전화", "USED_FOR", "통신") in c.grounding
    assert ("카메라", "USED_FOR", "촬영") in c.grounding  # cites where it drew from


def test_break_explains_the_broken_premise():
    e = CreativeEngine(CURATED)
    c = e.break_assumption("교육", "HAPPENS_AT", "학교")
    assert c is not None and c.creative_score > 0
    text = c.explain()
    assert "파괴된 전제" in text and "학교" in text and "영감(근거)" in text


def test_self_generates_its_own_problems():
    e = CreativeEngine(CURATED)
    qs = e.self_questions(3)
    assert len(qs) == 3 and all("왜" in q for q in qs)


def test_invent_is_deterministic():
    a = [c.name_hint for c in CreativeEngine(CURATED).invent(top=3)]
    b = [c.name_hint for c in CreativeEngine(CURATED).invent(top=3)]
    assert a == b


def test_break_on_unknown_triple_returns_none():
    e = CreativeEngine(CURATED)
    assert e.break_assumption("전화", "USED_FOR", "존재하지않는것") is None


_REL = (
    pathlib.Path(__file__).resolve().parents[3]
    / "data" / "cloud_brain" / "candidate_runs" / "clean_retrain_v1"
)


@pytest.mark.skipif(not (_REL / "relations.jsonl").exists(), reason="real graph not present")
def test_runs_on_real_graph_and_grounds_every_output():
    name = {}
    for line in (_REL / "concepts.jsonl").open(encoding="utf-8"):
        d = json.loads(line)
        name[d["concept_id"]] = d.get("canonical_name") or d["concept_id"]
    trips = []
    for line in (_REL / "relations.jsonl").open(encoding="utf-8"):
        d = json.loads(line)
        s, o, r = name.get(d["source_concept_id"]), name.get(d["target_concept_id"]), d.get("relation")
        if s and o and r:
            trips.append((s, r, o))
    assert len(trips) > 100
    engine = CreativeEngine(trips)
    ideas = engine.invent(top=5, max_pairs=3000)
    assert ideas, "engine produced no creative concepts on the real graph"
    for idea in ideas:
        assert idea.grounding, "a creative concept must cite the graph structure it came from"
        assert idea.creative_score > 0
        assert "파괴된 전제" in idea.explain()
