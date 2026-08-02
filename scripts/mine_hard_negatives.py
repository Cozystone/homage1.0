# -*- coding: utf-8 -*-
"""TCT target 1 — mine HARD NEGATIVES for the answerability head. The head is stuck at AUC 0.68 and
saturated (~1.0 everywhere) because at train time it mostly saw EASY negatives (obviously-irrelevant
passages), so it never learned the hard boundary: "the passage is ON TOPIC but does NOT contain the
answer." That is exactly the deployment distribution (a lexical retriever hands it on-topic-but-wrong
passages). We mine three tiers of negatives from SQuAD 2.0 + the passage pool and emit a balanced
(question, passage, answerable) training set the head has been missing. No training here — just the data.

  python scripts/mine_hard_negatives.py [n_questions]   -> data/graph_scale/answerability_hardneg.jsonl
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_TOK = re.compile(r"[A-Za-z0-9]+")


def _toks(s):
    return set(w.lower() for w in _TOK.findall(str(s)) if len(w) > 2)


def main():
    from packages.reasoning_vm.ace import data as D
    t0 = time.time()
    nq = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    HARD_K = int(sys.argv[2]) if len(sys.argv) > 2 else 3        # hard negatives per answerable question
    rng = random.Random(0)
    rows = D.load_squad("train")
    rng.shuffle(rows)
    rows = rows[:nq]

    # inverted index (token → passage ids) for FAST hard-negative retrieval (on-topic, wrong-answer)
    from collections import defaultdict
    passages = list({r["ctx"] for r in rows})
    ptoks = [_toks(p) for p in passages]
    inv: dict[str, list[int]] = defaultdict(list)
    for i, pt in enumerate(ptoks):
        for w in pt:
            inv[w].append(i)

    out = []
    tiers = {"pos": 0, "hard_lexical_topk": 0, "impossible": 0}
    for r in rows:
        q, ctx = str(r["q"]), str(r["ctx"])
        qt = _toks(q)
        if r["answerable"]:
            out.append({"q": q, "ctx": ctx, "answerable": 1}); tiers["pos"] += 1
            # HARD NEG tier 2: the TOP-K lexically most-similar OTHER passages (share topic, lack the
            # answer) — richer boundary signal than a single hardest one.
            cand: dict[int, int] = defaultdict(int)
            for w in qt:
                for i in inv.get(w, ()):
                    cand[i] += 1
            ranked = sorted(((ov, i) for i, ov in cand.items() if passages[i] != ctx and ov >= 2),
                            reverse=True)[:HARD_K]
            for _ov, i in ranked:
                out.append({"q": q, "ctx": passages[i], "answerable": 0, "tier": "lexical_topk"})
                tiers["hard_lexical_topk"] += 1
        else:
            # SQuAD2 is_impossible: on-topic passage, adversarially authored to lack the answer (tier 3)
            out.append({"q": q, "ctx": ctx, "answerable": 0, "tier": "impossible"}); tiers["impossible"] += 1

    rng.shuffle(out)
    outp = REPO / "data" / "graph_scale" / "answerability_hardneg.jsonl"
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fh:
        for ex in out:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    pos = sum(1 for e in out if e["answerable"] == 1)
    rep = {"examples": len(out), "positive_frac": round(pos / max(1, len(out)), 3), "tiers": tiers,
           "out": str(outp.relative_to(REPO)), "elapsed_s": round(time.time() - t0, 1),
           "note": "hard negatives = on-topic-but-no-answer (lexical_topk + SQuAD2 impossible); the exact "
                   "boundary the saturated head never learned. Feed to ace_train_squad with an answerability-"
                   "weighted loss."}
    print("RESULT mine_hardneg", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
