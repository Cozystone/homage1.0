# -*- coding: utf-8 -*-
"""Relation miner: pattern precision, both-known gate, judge integration."""
from __future__ import annotations

from packages.graph_scale.relation_miner import mine_relations
from packages.graph_scale.triple_store import TripleStore


def _store_with_prose(tmp_path):
    ts = TripleStore(tmp_path / "kg")
    ts.bulk_ingest([
        ("지진", "defined_as", "땅이 흔들리는 현상"),
        ("해일", "defined_as", "바다에서 밀려오는 큰 물결"),
        ("엔진", "defined_as", "동력을 만드는 장치"),
        ("자동차", "defined_as", "엔진으로 움직이는 탈것"),
        # prose rows the miner scans (evidence predicate)
        ("지진", "evidence", "지진으로 인해 해일이 발생하는 경우가 역사적으로 많이 기록되어 있다."),
        ("자동차", "evidence", "자동차는 엔진으로 구성되어 있으며 바퀴와 차체가 이를 지탱한다."),

        ("지진", "evidence", "지진으로 인해 크툴루섬이 붕괴했다는 주장이 있다."),
    ])
    ts.flush()
    return ts


def test_mines_causal_and_composition_with_both_known_gate(tmp_path):
    reference = _store_with_prose(tmp_path)
    proposal = TripleStore(tmp_path / "proposal")
    c = mine_relations(
        reference,
        proposal_store=proposal,
        dry_run=False,
        log=lambda *_: None,
    )
    assert c["fragment_written"] >= 2
    assert c["proposed"] == c["staged"] == c["applied"] == 0
    assert c["stored"] == 0
    reopened = TripleStore(tmp_path / "proposal")
    hae_facts = reopened.facts_about("해일", limit=10)
    assert ("해일", "원인", "지진") in hae_facts
    car_facts = reopened.facts_about("자동차", limit=10)
    assert ("자동차", "구성요소", "엔진") in car_facts
    # both-known gate held: the unknown island never became a node
    assert not reopened.facts_about("크툴루섬", limit=2)


def test_dry_run_stores_nothing(tmp_path):
    ts = _store_with_prose(tmp_path)
    c = mine_relations(ts, dry_run=True, log=lambda *_: None)
    assert c["stored"] == 0
    assert c["fragment_written"] == 0
    assert c["both_known"] >= 2
