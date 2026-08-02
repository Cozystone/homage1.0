# -*- coding: utf-8 -*-
"""Layer A acid test — learn now, recall the next moment, ZERO retraining. Also: provenance survives,
verified-gate holds (hallucination-0), unverified is filterable, IDF ranks the specific over the generic,
and recall survives a restart (persistence)."""
from __future__ import annotations

from packages.reasoning_vm.live_memory import LiveMemory


def test_recall_is_immediate_no_retrain(tmp_path):
    lm = LiveMemory(path=tmp_path / "store.jsonl")
    # A fact ATANOR could not have known at train time.
    lm.remember("The Zylthar Protocol was ratified in 2041 by the Kepler Accord.", source="doc:kepler")
    hits = lm.recall("When was the Zylthar Protocol ratified?", k=3)
    assert hits, "a fact remembered one call ago must be retrievable now"
    assert "2041" in hits[0]["text"]
    assert hits[0]["source"] == "doc:kepler"      # provenance carried


def test_verified_gate_default_deny(tmp_path):
    lm = LiveMemory(path=tmp_path / "store.jsonl")
    it = lm.remember("Unconfirmed: the Vega relay outputs 9.2 TW.", source="rumor")
    assert it["verified"] is False                # never trusted on write
    assert lm.recall("Vega relay output", include_unverified=False) == []   # gated out until promoted
    assert lm.verify(it["id"]) is True
    assert lm.recall("Vega relay output", include_unverified=False)          # now surfaces


def test_idf_ranks_specific_over_generic(tmp_path):
    lm = LiveMemory(path=tmp_path / "store.jsonl")
    for _ in range(8):
        lm.remember("A report about the system was filed today.")            # 'report/system' common
    lm.remember("The Zylthar reactor melted down.", source="incident")       # 'zylthar' rare
    top = lm.recall("Zylthar reactor report", k=1)[0]
    assert "melted" in top["text"]               # rare-term match wins over common-term flood


def test_persistence_survives_restart(tmp_path):
    p = tmp_path / "store.jsonl"
    LiveMemory(path=p).remember("Poseidonis is the capital of Atlantis.", source="atlas")
    reborn = LiveMemory(path=p)                   # fresh process, no in-RAM state
    hits = reborn.recall("capital of Atlantis", k=1)
    assert hits and "Poseidonis" in hits[0]["text"]
