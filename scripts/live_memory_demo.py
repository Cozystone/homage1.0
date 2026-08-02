# -*- coding: utf-8 -*-
"""Layer A measurement — the honest LLM-differentiator. A frozen parametric model CANNOT learn a new fact
after training; its weights are sealed. ATANOR + live memory learns a fact at INFERENCE time (a write to the
content index, zero gradient steps) and the frozen ACE span reader can answer it the next moment.

We measure span-F1 on NOVEL facts (invented entities that cannot exist in any training corpus) under two
conditions, same frozen reader:
  • closed-book  — reader sees the question only (what a parametric model must rely on) → expect ~0.
  • live-memory  — remember(fact) then recall(question) → top passage → span extract → expect high.
The delta is the measured worth of real-time memory. Also reports recall@1 (did the associative index put
the right fact on top?), isolating the retrieval organ from the span organ. No LLM, no retraining.

  python scripts/live_memory_demo.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_ART = {"a", "an", "the"}

# Invented facts — the entities/numbers cannot be in any pretraining corpus, so parametric recall is
# impossible by construction. (question, fact_text, gold_answer_span)
CASES = [
    ("Who ratified the Zylthar Protocol?",
     "The Zylthar Protocol was ratified in 2041 by the Kepler Accord assembly.", "Kepler Accord"),
    ("In what year was the Zylthar Protocol ratified?",
     "The Zylthar Protocol was ratified in 2041 by the Kepler Accord assembly.", "2041"),
    ("What is the capital of Atlantis?",
     "Poseidonis is the capital of Atlantis and its largest harbor city.", "Poseidonis"),
    ("How much power does the Vega relay output?",
     "The Vega relay outputs 9.2 terawatts at peak load during solar maxima.", "9.2 terawatts"),
    ("Who discovered element Novium?",
     "Element Novium was discovered by Dr. Ilsa Brandt at the Halden lab.", "Dr. Ilsa Brandt"),
    ("What powers the Brandt engine?",
     "The Brandt engine is powered by condensed muon plasma in a toroidal core.", "condensed muon plasma"),
    ("Where is the Halden lab located?",
     "The Halden lab is located beneath the Frostmarch glacier in northern Veil.", "Frostmarch glacier"),
    ("What is the mascot of the Quorval Institute?",
     "The Quorval Institute's mascot is a silver basilisk named Ferro.", "silver basilisk"),
    ("How many moons orbit Threnody?",
     "The planet Threnody is orbited by seven moons, the largest called Wren.", "seven"),
    ("Who composed the Aurelian Suite?",
     "The Aurelian Suite was composed by Mira Sole for the Veil coronation.", "Mira Sole"),
    ("What alloy is the Sundent blade made of?",
     "The Sundent blade is forged from a cobalt-iridium alloy quenched in brine.", "cobalt-iridium alloy"),
    ("What treaty ended the Marrow War?",
     "The Marrow War ended with the Treaty of Ashfall signed at Cindra keep.", "Treaty of Ashfall"),
]


def _norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(pred, gold):
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    c = sum((Counter(p) & Counter(g)).values())
    if not c:
        return 0.0
    pr, rc = c / len(p), c / len(g)
    return 2 * pr * rc / (pr + rc)


def main():
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    from packages.reasoning_vm.live_memory import LiveMemory
    t0 = time.time()
    print("loading frozen ACE reader (ace_hotpot.pt)…", flush=True)
    rd = MultiHopReader(ckpt="ace_hotpot.pt")

    # Fresh, isolated live store for the demo (does not touch the real one).
    store = REPO / "data" / "graph_scale" / "live_memory" / "_demo_store.jsonl"
    if store.exists():
        store.unlink()
    lm = LiveMemory(path=store)

    closed_f1 = live_f1 = recall_at1 = 0.0
    n = len(CASES)
    # 1) LEARN — write every fact once (inference-time, zero gradient steps).
    for _q, fact, _a in CASES:
        lm.remember(fact, source="live-demo")
    # 2) ANSWER — same frozen reader, two conditions.
    for q, fact, gold in CASES:
        # closed-book: no evidence (question as self-context) — what a sealed parametric model leans on
        cb, _ = rd._span(q, q)
        closed_f1 += _f1(cb, gold)
        # live-memory: associatively recall, extract span from the top passage
        hits = lm.recall(q, k=1)
        top = hits[0]["text"] if hits else ""
        recall_at1 += float(_norm(fact) == _norm(top))
        lv, _ = rd._span(q, top) if top else ("", 0.0)
        live_f1 += _f1(lv, gold)

    rep = {"benchmark": "novel-fact QA (Layer A live memory vs closed-book, same frozen reader)",
           "n": n,
           "closed_book_F1": round(closed_f1 / n, 4),
           "live_memory_F1": round(live_f1 / n, 4),
           "recall@1": round(recall_at1 / n, 4),
           "retraining_steps": 0,
           "claim": "facts unlearnable by a frozen parametric model are answered at inference via a write "
                    "to the live index — real-time learning without a gradient step.",
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT live_memory", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"live_memory_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    if store.exists():
        store.unlink()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
