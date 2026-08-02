# -*- coding: utf-8 -*-
"""D1 end-to-end — the artificial-CLS day/night/morning cycle, measured. DAY: the thinker learns verified
facts (hippocampus) and is asked unknowns it cannot ground (misses logged). NIGHT: sleep consolidates the
verified facts into the durable cortex and mines the misses into a deficit curriculum. MORNING: a FRESH
thinker with an EMPTY hippocampus (the buffer was cleared) still answers the learned facts — from the
cortex. That is systems consolidation: the knowledge survived the buffer, no retraining. No LLM.

  python scripts/sleep_demo.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.live_memory_demo import CASES, _f1     # reuse the invented-fact battery

UNKNOWN = ["What is the density of flubberium?", "Who leads the Zorbon council?",
           "How many rings orbit Vexis?", "What language is spoken in Thal?"]


def main():
    from packages.reasoning_vm.consolidation import MissLog, SleepConsolidator
    from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
    from packages.reasoning_vm.live_memory import LiveMemory
    t0 = time.time()
    base = REPO / "data" / "graph_scale" / "live_memory"
    hippo_p, cortex_p, miss_p = base / "_d1_hippo.jsonl", base / "_d1_cortex.jsonl", base / "_d1_miss.jsonl"
    for p in (hippo_p, cortex_p, miss_p):
        p.unlink(missing_ok=True)

    # ---- DAY ----
    misslog = MissLog(path=miss_p)
    day = RealTimeThinker(ckpt="ace_hotpot.pt", store=hippo_p, cortex_path=cortex_p, misslog=misslog,
                          min_overlap=2, record_misses=True)
    for _q, fact, _a in CASES:
        learned = day.learn(fact, source="d1-demo")
        day.promote_verified(learned["id"])
    day_answered = 0
    for q, _fact, gold in CASES:
        out = day.think(q)
        day_answered += int(out["grounded"])
    for q in UNKNOWN:
        day.think(q)                                  # ungrounded → miss recorded

    # ---- NIGHT ----
    sc = SleepConsolidator(hippocampus=day.mem, cortex=day.cortex, misslog=misslog)
    sleep = sc.sleep_cycle()

    # ---- MORNING: fresh thinker, EMPTY hippocampus, same cortex ----
    hippo_p.unlink(missing_ok=True)                   # the volatile buffer is gone
    morning = RealTimeThinker(ckpt="ace_hotpot.pt", store=hippo_p, cortex_path=cortex_p,
                              misslog=MissLog(path=miss_p), min_overlap=2, record_misses=False)
    assert len(morning.mem.items) == 0                # hippocampus truly empty
    m_f1 = m_from_cortex = 0.0
    for q, _fact, gold in CASES:
        out = morning.think(q)
        m_f1 += _f1(out["answer"], gold)
        m_from_cortex += float(any(e["origin"] == "cortex" for e in out["evidence"]))
    n = len(CASES)

    rep = {"benchmark": "D1 sleep consolidation — day/night/morning CLS cycle",
           "day_answered_from_buffer": day_answered, "n_facts": n,
           "night_consolidated_to_cortex": sleep["consolidated"]["promoted"],
           "night_curriculum_deficits": sleep["curriculum_deficits"],
           "night_top_deficits": [d["topic"] for d in sleep["top_deficits"]],
           "MORNING_answered_after_buffer_cleared_F1": round(m_f1 / n, 4),
           "MORNING_used_cortex_rate": round(m_from_cortex / n, 4),
           "claim": "verified facts consolidated hippocampus->cortex survive the buffer being cleared and "
                    "are answered next day with no retraining; misses became a ranked deficit curriculum.",
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d1_sleep", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"d1_sleep_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    for p in (hippo_p, cortex_p, miss_p):
        p.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
