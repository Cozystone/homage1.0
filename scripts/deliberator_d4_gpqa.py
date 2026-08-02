# -*- coding: utf-8 -*-
"""DELIBERATOR D4 — the full reasoning circuit meets GPQA-Diamond. Does the LEARNED support-head
adjudicator (which got SciQ 0.775) beat the word-overlap 0.146 / guess 0.25 on Google-proof PhD MCQ?

Two modes: closed-book (option scored by the support head with the question as context) and open-book
(retrieve an enwiki passage per question, adjudicate against it). GPQA stays SEALED — only topic tokens
and aggregate scores are printed/written; question text/choices/answers are never emitted or committed.
First gate: strict_acc > 0.25. Honest: GPQA is retrieval-adversarial; a null here is a real finding.

  python scripts/deliberator_d4_gpqa.py [openbook]   # add 'openbook' to retrieve enwiki evidence
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CSV = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"


def _shuffled(q, cor, inc):
    seed = int(hashlib.sha256(q.encode()).hexdigest(), 16)
    opts = [cor] + list(inc)
    order = list(range(4))
    for i in range(3, 0, -1):
        seed, j = divmod(seed, i + 1)
        order[i], order[j] = order[j], order[i]
    letters = "ABCD"
    return {letters[k]: str(opts[order[k]]).strip() for k in range(4)}, letters[order.index(0)]


def main():
    from packages.reasoning_vm.deliberator.adjudicator import Adjudicator
    t0 = time.time()
    openbook = "openbook" in sys.argv
    adj = Adjudicator(ckpt="ace_support.pt")
    passages = None
    if openbook:
        from packages.reasoning_vm.openbook import load_passages, retrieve
        pf = os.environ.get("PASSAGES_TSV") or str(REPO / "data" / "graph_scale" / "wiki_passages_en" / "passages.tsv")
        print(f"loading passages {pf}…", flush=True)
        passages = load_passages(pf)

    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    total = correct = 0
    for r in rows:
        q = str(r.get("Question") or "").strip()
        cor = str(r.get("Correct Answer") or "").strip()
        inc = [str(r.get(f"Incorrect Answer {i}") or "").strip() for i in (1, 2, 3)]
        if not q or not cor or not all(inc):
            continue
        options, gold = _shuffled(q, cor, inc)
        if openbook:
            got = retrieve(q, passages)
            ev = got[1] if got else q
        else:
            ev = q                                          # closed-book: question as self-context
        pred = adj.answer(q, options, ev)
        total += 1
        correct += int(pred == gold)
    acc = correct / max(1, total)
    rep = {"benchmark": f"GPQA-Diamond ({'open' if openbook else 'closed'}-book, ACE-support adjudicator)",
           "n": total, "strict_acc": round(acc, 4), "guess": 0.25, "word_overlap_prev": 0.146,
           "gate>guess": acc > 0.25, "elapsed_s": round(time.time() - t0, 1),
           "honest_note": "GPQA is Google-proof PhD MCQ; retrieval-adversarial. Topic tokens only; "
                          "questions never stored (license + sealed)."}
    print("\nRESULT d4", json.dumps(rep))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"deliberator_d4_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")   # aggregate only — not committed (reports gitignored)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
