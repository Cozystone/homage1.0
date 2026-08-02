# -*- coding: utf-8 -*-
"""Polysemy hub splitting — induction, context resolution, fact filtering."""

from __future__ import annotations

import packages.graph_scale.sense_split as ss

_DEFS = [
    "사람을 몹시 좋아함 또는 그런 마음이나 상태",
    "어떤 사람을 몹시 좋아함 또는 그런 마음이나 상태",
    "한국의 가옥 구조에서 아낙이 머무는 안채와 떨어져 바깥주인이 소일하는 방 또는 거처",
]


def test_polysemy_detected_and_clustered():
    senses = ss.induce_senses("사랑", definitions=_DEFS)
    assert len(senses) == 2
    # dominant sense first (described by more definitions)
    assert "좋아함" in senses[0].gloss
    assert "가옥" in senses[1].signature or "안채" in senses[1].signature


def test_monosemous_term_never_splits():
    senses = ss.induce_senses("바다", definitions=[
        "지구의 표면에 넓게 소금기가 있는 물이 고여 있는 곳",
        "지구 표면에서 소금물이 넓게 고인 곳",
    ])
    assert len(senses) == 1


def test_context_resolves_the_house_sense(monkeypatch):
    monkeypatch.setattr(ss, "_kg_definitions", lambda t: [])
    senses = ss.induce_senses("사랑", definitions=_DEFS)
    ch = ss.resolve_sense("사랑", "안채 옆에 있는 사랑 말이야", senses=senses)
    assert "가옥" in ch.gloss or "안채" in ch.gloss
    ch2 = ss.resolve_sense("사랑", "사랑이라는 감정은 왜 생겨", senses=senses)
    assert "좋아함" in ch2.gloss


def test_one_hop_expansion_resolves_indirect_context(monkeypatch):

    monkeypatch.setattr(ss, "_kg_definitions",
                        lambda t: ["한국의 전통 가옥"] if t == "한옥" else [])
    senses = ss.induce_senses("사랑", definitions=_DEFS)
    ch = ss.resolve_sense("사랑", "한옥에서 사랑은 어디 있어", senses=senses)
    assert "가옥" in ch.gloss


def test_no_signal_falls_to_dominant_never_random(monkeypatch):
    monkeypatch.setattr(ss, "_kg_definitions", lambda t: [])
    senses = ss.induce_senses("사랑", definitions=_DEFS)
    ch = ss.resolve_sense("사랑", "그거 말이야", senses=senses)
    assert ch.sense_id == senses[0].sense_id  # the graph's own prior


def test_sense_filtered_facts_drops_other_senses(monkeypatch):
    monkeypatch.setattr(ss, "_kg_definitions", lambda t: [])
    senses = ss.induce_senses("사랑", definitions=_DEFS)
    rows = [("사랑", "defined_as", d, "src", "url") for d in _DEFS]
    kept = ss.sense_filtered_facts("사랑", "감정으로서의 사랑", rows, senses=senses)
    texts = [r[2] for r in kept]
    assert all("가옥" not in t for t in texts)
    assert any("좋아함" in t for t in texts)
