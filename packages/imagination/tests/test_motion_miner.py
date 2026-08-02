# -*- coding: utf-8 -*-
"""The kinetic ear: consensus sentences that NAME a motion become motion-ledger triples — mined
from natural language via the compiler's shared vocabulary, never a hard-coded narrative table."""
from pathlib import Path

import packages.imagination.motion_miner as mm


def test_transitive_orbit_with_anchor():
    rels = mm.mine_motion_relations("달은 지구 주위를 돈다.")
    assert any(r["motion"] == "orbit" and r["subject"] == "달" and r["object"] == "지구"
               for r in rels)


def test_intransitive_fall():
    rels = mm.mine_motion_relations("가을이 오면 사과가 떨어진다.")
    assert any(r["motion"] == "fall" and r["subject"] == "사과" and r["object"] is None
               for r in rels)


def test_transitive_attract():
    rels = mm.mine_motion_relations("지구는 달을 끌어당긴다.")
    assert any(r["motion"] == "attract" and r["subject"] == "지구" and r["object"] == "달"
               for r in rels)


def test_non_kinetic_sentence_yields_nothing():
    assert mm.mine_motion_relations("서울은 대한민국의 수도이다.") == []


def test_record_dedupes_and_carries_provenance(tmp_path):
    mm._LEDGER = tmp_path / "motion.jsonl"
    cands = [{"text": "달은 지구 주위를 돈다.", "domains": ["a.org", "b.org"]}] * 3
    assert mm.record_from_consensus(cands) == 1            # deduped to one triple
    entries = mm._load()
    assert entries[0]["domains"] == ["a.org", "b.org"]      # provenance carried
    assert mm.motion_relations_for({"달"}) and mm.motion_relations_for({"지구"})
    assert mm.motion_relations_for({"화성"}) == []
