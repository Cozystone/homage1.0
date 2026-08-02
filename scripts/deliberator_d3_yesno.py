# -*- coding: utf-8 -*-
"""DELIBERATOR D3.1 probe — can the EXISTING support head answer HotpotQA yes/no (comparison) questions
without any new training? ~6% of HotpotQA is yes/no, which the span reader structurally cannot answer. But
a yes/no question is a claim to be verified: score support(question, gold_evidence) and read yes if
SUPPORTS outweighs REFUTES. This reuses the judge organ (No-LLM, no new head) — measure before building.

Isolates the comparison ability from retrieval by scoring over GOLD evidence. Reports accuracy vs the
majority ("always yes") baseline. If it clears majority, the organ transfers; if not, a boolean head is
justified.

  python scripts/deliberator_d3_yesno.py [n]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    import pandas as pd
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    df = pd.read_parquet(REPO / "data" / "benchmarks" / "hotpotqa" / "dev_distractor.parquet")
    print("loading support head (ace_support.pt)…", flush=True)
    rd = MultiHopReader(ckpt="ace_support.pt")                       # D0/D1 support judge

    yn = []
    for _i, r in df.iterrows():
        if str(r["answer"]).lower() not in ("yes", "no"):
            continue
        ctx = r["context"]
        titles, sents = list(ctx["title"]), list(ctx["sentences"])
        gold = set(str(t) for t in r["supporting_facts"]["title"])
        ev = " ".join(" ".join(str(x) for x in sents[j]) for j in range(len(titles))
                      if str(titles[j]) in gold)
        if ev:
            yn.append((str(r["question"]), ev, str(r["answer"]).lower()))
        if len(yn) >= n:
            break

    n_yes = sum(1 for _q, _e, a in yn if a == "yes")
    maj = max(n_yes, len(yn) - n_yes) / max(1, len(yn))             # "always the majority class"
    correct = 0
    for q, ev, gold in yn:
        probs = rd._support(q, [ev])[0]                             # [P_SUPPORTS, P_NEI, P_REFUTES]
        pred = "yes" if probs[0] >= probs[2] else "no"
        correct += int(pred == gold)
    acc = correct / max(1, len(yn))

    rep = {"probe": "HotpotQA yes/no via existing support head (no new training)", "n_yesno": len(yn),
           "yes_frac": round(n_yes / max(1, len(yn)), 3), "majority_baseline": round(maj, 4),
           "support_head_acc": round(acc, 4), "beats_majority": acc > maj,
           "verdict": ("support head transfers to comparison — wire it in" if acc > maj
                       else "does not clear majority — a trained boolean head is justified"),
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d3.1_yesno", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"deliberator_d3_yesno_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
