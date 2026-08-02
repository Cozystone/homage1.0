# -*- coding: utf-8 -*-
import json

from packages.flywheel import self_improvement as si


_ROWS = [
    {"q": "고래는 물고기야?", "a": "아니요, 고래는 물고기가 아니라 동물의 한 종류예요. 확인된 분류로는 동물입니다.",
     "kind": "verified_isa", "conf": 0.6, "lane": "verified_isa", "router": "verify", "gold_intent": "verify"},
    {"q": "인공지능이 뭐야?", "a": "인공지능은 지능을 갖춘 컴퓨터 시스템입니다. 머신러닝은 데이터에서 패턴을 학습합니다.",
     "kind": "grounded_neighborhood_synthesis", "conf": 0.4, "lane": "base_brain", "router": "definition", "gold_intent": "definition"},
    {"q": "지금 몇 시야?", "a": "현재 기본 지식만으로는 실시간 근거가 부족합니다.",
     "kind": "abstained", "conf": 0.1, "lane": "abstain", "router": "definition", "gold_intent": "realtime"},
]


def test_diagnose_reads_failures_and_weak_lanes():
    d = si.diagnose(_ROWS)
    assert d["turns"] == 3
    assert d["weak_turns"] >= 1                # the abstain turn is weak
    assert any("abstain" in str(lane).lower() or lane == "abstain" for lane, _ in d["weak_lanes"])


def test_router_readiness_measures_agreement_and_gates_promotion():
    rr = si.router_readiness(_ROWS)
    # 2 of 3 shadow predictions match gold (verify, definition); realtime missed
    assert rr["samples"] == 3
    assert 0.6 <= rr["agreement"] <= 0.7
    assert rr["ready_to_replace_rules"] is False       # below 0.75 and < 200 samples
    assert "realtime" in dict(rr["weakest_intents"])   # the missed intent surfaces


def test_harvest_turns_own_factual_answers_into_examples():
    ex = si.harvest_discourse_examples(_ROWS)
    # factual turns with >=2 grounded sentences become (facts, question) examples;
    # the abstain turn (boilerplate) is excluded
    qs = [q for _facts, q in ex]
    assert "고래는 물고기야?" in qs
    assert "지금 몇 시야?" not in qs
