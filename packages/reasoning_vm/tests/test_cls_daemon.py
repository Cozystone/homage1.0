# -*- coding: utf-8 -*-
"""One autonomous CLS cycle: a recorded miss drives a gated curiosity harvest, and the freshly-learned
verified fact is consolidated into cortex — all in a single run_cycle(). Consolidation-only (no harvester)
also runs safely."""
from __future__ import annotations

from packages.reasoning_vm.cls_daemon import run_cycle
from packages.reasoning_vm.consolidation import MissLog, SleepConsolidator
from packages.reasoning_vm.curiosity import CuriosityEngine
from packages.reasoning_vm.live_memory import LiveMemory


def _rig(tmp):
    hippo = LiveMemory(path=tmp / "h.jsonl")
    cortex = LiveMemory(path=tmp / "c.jsonl")
    misslog = MissLog(path=tmp / "m.jsonl")
    return SleepConsolidator(hippocampus=hippo, cortex=cortex, misslog=misslog), hippo, cortex, misslog


def test_cycle_curiosity_then_consolidate(tmp_path):
    sc, hippo, cortex, misslog = _rig(tmp_path)
    misslog.record("What is the density of flubberium?", grounded=False)
    harv = lambda topic: ([{"text": "Flubberium density is 4.2.", "source": "a"},
                           {"text": "Flubberium density is 4.2.", "source": "b"}]
                          if "flubberium" in topic else [])
    cur = CuriosityEngine(memory=hippo, harvester=harv)
    rep = run_cycle(sc, cur)
    assert rep["curiosity_learned"] >= 1                       # gated harvest learned a fact
    assert rep["consolidated"] >= 1                            # and it consolidated to cortex
    assert any("Flubberium" in i["text"] for i in cortex.items)


def test_cycle_consolidation_only_no_harvester(tmp_path):
    sc, hippo, cortex, misslog = _rig(tmp_path)
    hippo.remember("Poseidonis is the capital of Atlantis.", source="atlas", verified=True)
    rep = run_cycle(sc, curiosity=None)                        # no web — still consolidates safely
    assert rep["curiosity_learned"] == 0 and rep["consolidated"] == 1
