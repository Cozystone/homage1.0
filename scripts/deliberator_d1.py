# -*- coding: utf-8 -*-
"""DELIBERATOR D1 — does the learned SUPPORT head (D0) actually pick MCQ answers? SciQ ships a support
passage per question, so this isolates the ADJUDICATOR (organ ⑥) from retrieval: each option becomes a
claim, ACE scores net support (P(SUPPORTS)−P(REFUTES)), argmax wins. Honest caveat: SciTail (a D0 source)
is derived from science questions, so this is domain-transfer, not a pristine holdout — reported as such.

  python scripts/deliberator_d1.py [n]
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_HDR = {"User-Agent": "ATANOR-eval (research; blueyjkim@gmail.com)"}
CACHE = REPO / "data" / "benchmarks" / "sciq"


def _dl(url, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=_HDR), timeout=180).read())
    return path


def main():
    import pandas as pd
    from packages.reasoning_vm.deliberator.adjudicator import Adjudicator
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    df = pd.read_parquet(_dl(
        "https://huggingface.co/datasets/allenai/sciq/resolve/refs%2Fconvert%2Fparquet/default/test/0000.parquet",
        CACHE / "test.parquet"))
    print(f"loading adjudicator (ACE support head)…", flush=True)
    adj = Adjudicator()
    keys = "ABCD"
    rng = random.Random(0)
    correct = answered = with_ev = 0
    total = 0
    for _i, r in df.iterrows():
        if total >= n:
            break
        support = str(r.get("support") or "").strip()
        opts_text = [str(r["correct_answer"]), str(r["distractor1"]),
                     str(r["distractor2"]), str(r["distractor3"])]
        if not all(opts_text):
            continue
        order = list(range(4)); rng.shuffle(order)
        options = {keys[j]: opts_text[order[j]] for j in range(4)}
        gold = keys[order.index(0)]
        ev = support if support else str(r["question"])     # no-support rows fall back to the question
        with_ev += bool(support)
        pred = adj.answer(str(r["question"]), options, ev)
        total += 1
        answered += 1
        correct += int(pred == gold)
    acc = correct / max(1, total)
    rep = {"benchmark": "SciQ-test(open-book, ACE-support adjudicator)", "n": total,
           "accuracy": round(acc, 4), "guess": 0.25, "vs_guess": round(acc - 0.25, 4),
           "had_support_passage": with_ev, "elapsed_s": round(time.time() - t0, 1),
           "caveat": "SciTail (a D0 train source) derives from science QA → domain-transfer, not pristine holdout",
           "gate>guess": acc > 0.30}
    print("\nRESULT d1", json.dumps(rep))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"deliberator_d1_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
