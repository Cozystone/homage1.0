# -*- coding: utf-8 -*-
"""D1 sleep consolidation: verified episodic facts consolidate hippocampus→cortex (dedup, provenance);
misses mine into a ranked deficit curriculum; unverified facts do NOT consolidate (hallucination-0)."""
from __future__ import annotations

from packages.reasoning_vm.consolidation import MissLog, SleepConsolidator
from packages.reasoning_vm.live_memory import LiveMemory


def _rig(tmp):
    hippo = LiveMemory(path=tmp / "hippo.jsonl")
    cortex = LiveMemory(path=tmp / "cortex.jsonl")
    misslog = MissLog(path=tmp / "miss.jsonl")
    return SleepConsolidator(hippocampus=hippo, cortex=cortex, misslog=misslog)


def test_verified_consolidates_unverified_does_not(tmp_path):
    sc = _rig(tmp_path)
    sc.hippo.remember("Poseidonis is the capital of Atlantis.", source="atlas", verified=True)
    sc.hippo.remember("Rumor: the Vega relay outputs 9 TW.", source="rumor", verified=False)
    con = sc.consolidate()
    assert con["promoted"] == 1                        # only the verified fact crosses to cortex
    texts = [it["text"] for it in sc.cortex.items]
    assert any("Poseidonis" in t for t in texts)
    assert not any("Vega" in t for t in texts)          # unverified stays out — hallucination-0


def test_consolidation_is_idempotent(tmp_path):
    sc = _rig(tmp_path)
    sc.hippo.remember("Element Novium was discovered by Dr. Brandt.", source="lab", verified=True)
    assert sc.consolidate()["promoted"] == 1
    assert sc.consolidate()["promoted"] == 0            # dedup: second sleep promotes nothing new


def test_misses_mine_ranked_curriculum(tmp_path):
    sc = _rig(tmp_path)
    for _ in range(3):
        sc.misslog.record("What is the density of flubberium?", grounded=False)
    sc.misslog.record("Who leads the Zorbon council?", grounded=False)
    deficits = sc.mine_curriculum(top_k=10)
    topics = [d["topic"] for d in deficits]
    assert "flubberium" in topics                       # the repeated deficit ranks in the curriculum
    top = max(deficits, key=lambda d: d["miss_count"])
    assert top["miss_count"] >= 3 and top["sample_questions"]


def test_sleep_cycle_reports(tmp_path):
    sc = _rig(tmp_path)
    sc.hippo.remember("The Aurelian Suite was composed by Mira Sole.", source="score", verified=True)
    sc.misslog.record("What alloy is the Sundent blade?", grounded=False)
    rep = sc.sleep_cycle()
    assert rep["consolidated"]["promoted"] == 1
    assert rep["misses_replayed"] == 1 and rep["curriculum_deficits"] >= 1
