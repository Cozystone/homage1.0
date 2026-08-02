# -*- coding: utf-8 -*-
"""Tier B / B1 — measure the L1 signal ALONE, before any GPU time (a red or weak result is a result).

Question: do the DrQA-style match features, with NO neural net, already locate the answer? For each
fresh-QA item we split the passage into sentences, score each by idf-weighted question overlap
(match_features.overlap_score), pick the top sentence, and check whether the gold answer span lies in
it. This is the answer-LOCATING signal the span head builds on; if L1 already finds the right sentence
often, the L2/L3 span head only has to extract within it, which is the from-scratch-DrQA story.

  python scripts/b1_l1_baseline.py [seed]
Reports sentence-selection accuracy on the sealed fresh QA. Pure CPU; touches no model.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from packages.reasoning_vm.ace.match_features import overlap_score, build_idf   # noqa: E402

_SENT = re.compile(r"(?<=[.!?])\s+")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260719
    qa = REPO / "data" / "benchmarks" / "b1_fresh" / f"qa_{seed}.jsonl"
    if not qa.exists():
        print(f"no fresh QA at {qa} — run scripts/b1_make_fresh_qa.py {'' if seed==20260719 else seed}")
        return 1
    items = [json.loads(l) for l in qa.read_text(encoding="utf-8").splitlines() if l.strip()]
    idf = build_idf([it["passage"] for it in items])

    hit = 0
    rand_hit = 0.0
    for it in items:
        sents = _SENT.split(it["passage"])
        # locate which sentence contains the gold span
        gold_sent = None
        off = 0
        for s in sents:
            j = it["passage"].find(s, off)
            if j <= it["answer_start"] < j + len(s):
                gold_sent = s
            off = j + len(s)
        best = max(sents, key=lambda s: overlap_score(it["question"], s, idf)) if sents else ""
        if best and best == gold_sent:
            hit += 1
        rand_hit += 1.0 / max(1, len(sents))               # a blind pick's expected accuracy

    n = len(items)
    print("=== B1 L1 signal — match-feature sentence selection (No-NN, CPU) ===")
    print(f"items {n}")
    print(f"sentence-selection accuracy : {hit / max(1, n):.4f}")
    print(f"blind-pick baseline         : {rand_hit / max(1, n):.4f}")
    print(f"lift over blind             : {(hit / max(1, n)) - (rand_hit / max(1, n)):+.4f}")
    print("\nread: L1 features alone locate the answer sentence this often. The L2/L3 span head then\n"
          "extracts within it — the from-scratch DrQA/BiDAF story (0.75 F1 without a pretrained LM).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
