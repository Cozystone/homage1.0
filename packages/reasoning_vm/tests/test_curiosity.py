# -*- coding: utf-8 -*-
"""D3 curiosity gates (the immune system that makes web-learning safe): single-source REJECTED, k-source
ACCEPTED, off-topic REJECTED; accepted facts are written verified so the next sleep can consolidate them."""
from __future__ import annotations

from packages.reasoning_vm.curiosity import CuriosityEngine
from packages.reasoning_vm.live_memory import LiveMemory


def _mock(table):
    return lambda topic: table.get(topic, [])


def test_consensus_gate_needs_k_sources(tmp_path):
    mem = LiveMemory(path=tmp_path / "m.jsonl")
    harv = _mock({"flubberium": [
        {"text": "Flubberium has density 4.2.", "source": "siteA"},
        {"text": "Flubberium has density 4.2.", "source": "siteB"},   # 2 distinct sources agree
        {"text": "Flubberium was invented by nobody.", "source": "siteC"},  # single source
    ]})
    eng = CuriosityEngine(memory=mem, harvester=harv)
    claims = eng.pursue("flubberium", min_sources=2)
    texts = [c["text"] for c in claims]
    assert any("density 4.2" in t for t in texts)         # 2-source claim passes
    assert not any("invented by nobody" in t for t in texts)   # single-source claim blocked


def test_relevance_gate_blocks_offtopic(tmp_path):
    mem = LiveMemory(path=tmp_path / "m.jsonl")
    harv = _mock({"zorbon": [
        {"text": "Paris is the capital of France.", "source": "a"},
        {"text": "Paris is the capital of France.", "source": "b"},   # 2 sources but OFF-TOPIC
    ]})
    eng = CuriosityEngine(memory=mem, harvester=harv)
    assert eng.pursue("zorbon", min_sources=2) == []       # no 'zorbon' anchor → rejected


def test_run_writes_verified_for_next_sleep(tmp_path):
    mem = LiveMemory(path=tmp_path / "m.jsonl")
    harv = _mock({"vexis": [
        {"text": "Vexis has three rings.", "source": "obs1"},
        {"text": "Vexis has three rings.", "source": "obs2"},
    ]})
    eng = CuriosityEngine(memory=mem, harvester=harv)
    rep = eng.run([{"topic": "vexis"}], min_sources=2)
    assert rep["facts_learned"] == 1
    it = [i for i in mem.items if "Vexis" in i["text"]][0]
    assert it["verified"] and it["source"].startswith("curiosity:")   # trusted (passed gates), provenanced
