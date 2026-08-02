# -*- coding: utf-8 -*-
"""The CLS organism, running on its own — "leave it and it grows", made literal + safe. On each cycle it
SLEEPS (D1: consolidate the day's verified facts hippocampus→cortex, mine the misses into a deficit
curriculum) and, if a harvester is wired, is CURIOUS (D3: pursue the top deficits through the relevance +
k-source immune gates, learning only verified facts). Bounded, logged, kill-switchable. The consolidation
half is useful with no web at all; curiosity activates when a harvester is configured. No LLM.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from packages.reasoning_vm.consolidation import CORTEX, HIPPO, MISSLOG, MissLog, SleepConsolidator
from packages.reasoning_vm.curiosity import CuriosityEngine, Harvester
from packages.reasoning_vm.live_memory import LiveMemory

_BASE = HIPPO.parent
KILL = _BASE / "cls_daemon.stop"          # touch this file to halt the organism (kill-switch)
LOG = _BASE / "cls_cycles.jsonl"


def run_cycle(consolidator: SleepConsolidator, curiosity: Optional[CuriosityEngine] = None,
              max_topics: int = 8, min_sources: int = 2) -> dict[str, Any]:
    """One autonomous cycle: sleep (always) → curiosity (if a harvester is wired). Safe + bounded."""
    t0 = time.time()
    curriculum = consolidator.mine_curriculum()
    learned, detail = 0, []
    if curiosity is not None and curriculum:
        curi = curiosity.run(curriculum, min_sources=min_sources, max_topics=max_topics)
        learned, detail = curi["facts_learned"], curi["detail"]
    sleep = consolidator.sleep_cycle()      # consolidate AFTER curiosity so freshly-learned facts promote
    return {"consolidated": sleep["consolidated"]["promoted"], "cortex_size": sleep["consolidated"]["cortex_size"],
            "deficits": len(curriculum), "curiosity_learned": learned, "curiosity_detail": detail,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": round(time.time() - t0, 2)}


def build(harvester: Harvester | None = None) -> tuple[SleepConsolidator, Optional[CuriosityEngine]]:
    """Wire the organism onto the REAL live-memory stores (hippocampus/cortex/misslog)."""
    hippo = LiveMemory(path=HIPPO)
    cortex = LiveMemory(path=CORTEX)
    misslog = MissLog(path=MISSLOG)
    sc = SleepConsolidator(hippocampus=hippo, cortex=cortex, misslog=misslog)
    cur = CuriosityEngine(memory=hippo, harvester=harvester) if harvester is not None else None
    return sc, cur


def loop(interval_s: float = 3600.0, harvester: Harvester | None = None, once: bool = False) -> int:
    """Run the organism forever (or once). Halts immediately if the kill-switch file exists."""
    sc, cur = build(harvester)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    while True:
        if KILL.exists():
            print("cls_daemon: kill-switch present — halting", flush=True)
            return 0
        rep = run_cycle(sc, cur)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, ensure_ascii=False) + "\n")
        print("cls_cycle", json.dumps(rep, ensure_ascii=False), flush=True)
        if once:
            return 0
        for _ in range(int(max(1, interval_s))):     # interruptible sleep (checks kill-switch each second)
            if KILL.exists():
                return 0
            time.sleep(1)
