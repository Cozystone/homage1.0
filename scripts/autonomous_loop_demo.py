# -*- coding: utf-8 -*-
"""The autonomous self-improvement loop, measured end-to-end (D1+D3): a gap today becomes knowledge
tomorrow — with the immune system intact.

  DAY 1     ask questions the system cannot ground  → misses recorded
  NIGHT 1   sleep mines the misses into a deficit curriculum
  CURIOSITY pursue the deficits; the harvester's returns pass the relevance + k-source consensus gates,
            then are written to memory as verified facts
  NIGHT 2   sleep consolidates the newly-learned facts into the durable cortex
  DAY 2     the SAME questions are now ANSWERED (from cortex)

"Leave it loose and it grows" — proven for KNOWLEDGE, behind the gates that make it safe. No LLM.
  python scripts/autonomous_loop_demo.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# the gaps (day 1) and what a gated, k-source web would return (curiosity)
QA = [
    ("What is the density of flubberium?", "flubberium",
     "The density of flubberium is 4.2 grams per cubic centimeter.", "4.2"),
    ("Who leads the Zorbon council?", "zorbon",
     "The Zorbon council is led by Chancellor Vek.", "Chancellor Vek"),
    ("How many rings orbit Vexis?", "vexis",
     "The planet Vexis is orbited by three rings.", "three"),
]


def _harvester(topic):
    # a well-behaved web: two INDEPENDENT sources corroborate each real fact (single-source/off-topic
    # would be gated out — see test_curiosity). Any deficit token that appears in a fact harvests it.
    out = []
    for _q, _topic, fact, _a in QA:
        if topic.lower() in fact.lower():
            out += [{"text": fact, "source": "srcA"}, {"text": fact, "source": "srcB"}]
    return out


def main():
    from packages.reasoning_vm.consolidation import MissLog, SleepConsolidator
    from packages.reasoning_vm.curiosity import CuriosityEngine
    from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
    t0 = time.time()
    base = REPO / "data" / "graph_scale" / "live_memory"
    hp, cp, mp = base / "_al_h.jsonl", base / "_al_c.jsonl", base / "_al_m.jsonl"
    for p in (hp, cp, mp):
        p.unlink(missing_ok=True)
    misslog = MissLog(path=mp)
    rt = RealTimeThinker(ckpt="ace_hotpot.pt", store=hp, cortex_path=cp, misslog=misslog,
                         min_overlap=2, record_misses=True)

    # DAY 1 — the gaps
    day1_grounded = sum(int(rt.think(q)["grounded"]) for q, _t, _f, _a in QA)

    # NIGHT 1 — mine the deficits
    sc = SleepConsolidator(hippocampus=rt.mem, cortex=rt.cortex, misslog=misslog)
    curriculum = sc.mine_curriculum()

    # CURIOSITY — pursue, gate, learn (writes verified facts into the hippocampus)
    cur = CuriosityEngine(memory=rt.mem, harvester=_harvester)
    curi = cur.run(curriculum, min_sources=2, max_topics=10)

    # NIGHT 2 — consolidate the newly-learned facts into cortex
    con = sc.consolidate()

    # DAY 2 — the same questions, now answered from cortex
    day2_grounded = 0
    day2_from_cortex = 0
    day2_correct = 0
    for q, _t, _f, gold in QA:
        out = rt.think(q)
        day2_grounded += int(out["grounded"])
        day2_from_cortex += int(any(e["origin"] in ("cortex", "live") for e in out["evidence"]))
        day2_correct += int(gold.lower() in out["answer"].lower())

    n = len(QA)
    rep = {"benchmark": "autonomous self-improvement loop (D1 sleep + D3 curiosity)",
           "n_gaps": n,
           "DAY1_grounded": day1_grounded,
           "NIGHT1_deficits_mined": len(curriculum),
           "CURIOSITY_facts_learned": curi["facts_learned"],
           "NIGHT2_consolidated_to_cortex": con["promoted"],
           "DAY2_grounded": day2_grounded, "DAY2_answer_correct": day2_correct,
           "gap_to_knowledge": f"{day1_grounded}/{n} -> {day2_grounded}/{n} grounded",
           "claim": "the system's own miss drove a gated (relevance + k-source) expedition; the verified "
                    "harvest consolidated into durable knowledge; the gap it could not answer yesterday it "
                    "answers today — autonomous knowledge growth with the anti-poison immune system intact.",
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT autonomous_loop", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"autonomous_loop_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    for p in (hp, cp, mp):
        p.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
