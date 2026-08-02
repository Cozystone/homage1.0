# -*- coding: utf-8 -*-
"""DELIBERATOR D3.1 — teach the span head MULTI-HOP extraction on HotpotQA train (the E-wall fix).

The extractive ceiling is 99.8% (the answer IS a span in the gold supporting paras); the SQuAD span head
just can't LOCATE it under a 2-hop question. So fine-tune the span head (warm-start from the MLM+SQuAD
backbone) on (question, gold-supporting-evidence → answer span). Eval reports BOTH: span F1 on GOLD
evidence (isolates the span organ) and the FULL pipeline (support-select + span). No LLM.

  python scripts/ace_train_hotpot.py [n_train] [epochs]
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import torch                                                          # noqa: E402
from packages.reasoning_vm import learned_discriminator as LD        # noqa: E402
from packages.reasoning_vm.ace import data as D                      # noqa: E402
from packages.reasoning_vm.ace.model import AceEncoder               # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
HP = REPO / "data" / "benchmarks" / "hotpotqa"
_ART = {"a", "an", "the"}


def _norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(pred, gold):
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    c = sum((Counter(p) & Counter(g)).values())
    return 0.0 if not c else 2 * (c / len(p)) * (c / len(g)) / (c / len(p) + c / len(g))


def _rows(split, n):
    import pandas as pd
    df = pd.read_parquet(HP / f"{split}.parquet")
    out = []
    for _i, r in df.iterrows():
        ans = str(r["answer"])
        ctx = r["context"]
        titles, sents = list(ctx["title"]), list(ctx["sentences"])
        goldT = set(str(t) for t in r["supporting_facts"]["title"])
        gold_ev = " ".join(" ".join(str(x) for x in sents[j]) for j in range(len(titles)) if str(titles[j]) in goldT)
        allp = [(str(titles[j]), " ".join(str(x) for x in sents[j])) for j in range(len(titles))]
        out.append({"q": str(r["question"]), "ans": ans, "gold_ev": gold_ev, "paras": allp,
                    "yesno": ans.lower() in ("yes", "no")})
        if len(out) >= n:
            break
    return out


def main():
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    print(f"device {DEV} | loading HotpotQA…", flush=True)
    tr = [r for r in _rows("train", n) if not r["yesno"]]
    enc = []
    for r in tr:                                                     # locate the answer span in gold evidence
        a0 = r["gold_ev"].lower().find(r["ans"].lower())
        if a0 < 0:
            continue
        e = D.encode(tok, r["q"], r["gold_ev"], a0, r["ans"])
        if e["has_span"]:
            enc.append(e)
    print(f"  {len(enc)} span-aligned train ({round(time.time()-t0,1)}s)", flush=True)

    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    sq = REPO / "data" / "graph_scale" / "ace_squad.pt"              # MLM+SQuAD backbone + span head
    if sq.exists():
        model.load_state_dict(torch.load(sq, map_location=DEV), strict=False)
        print("  warm-started from ace_squad.pt (MLM+SQuAD)", flush=True)
    model._tok = tok
    opt = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=0.01)
    ce = torch.nn.CrossEntropyLoss()
    bs = 16
    steps = ((len(enc) + bs - 1) // bs) * epochs
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    step = 0
    for ep in range(epochs):
        idx = list(range(len(enc)))
        random.Random(ep).shuffle(idx)
        model.train()
        for i in range(0, len(idx), bs):
            batch = [enc[j] for j in idx[i:i + bs]]
            b = D.collate(batch, tok)
            b = {k: v.to(DEV) for k, v in b.items()}
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                _ans, start, end = model(b["ids"], b["seg"], b["feats"], b["pad"])
                loss = 0.5 * (ce(start, b["start"]) + ce(end, b["end"]))
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 500 == 0:
                print(f"    step {step}/{steps} loss {loss.item():.4f} ({round(time.time()-t0,1)}s)", flush=True)
    torch.save(model.state_dict(), REPO / "data" / "graph_scale" / "ace_hotpot.pt")

    # eval: span F1 on GOLD evidence (isolates the span organ)
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    rd = MultiHopReader.__new__(MultiHopReader)
    rd.torch, rd.D, rd.dev, rd.tok, rd.model = torch, D, DEV, tok, model
    model.eval()
    dev = _rows("dev_distractor", 1500)
    gold_f1 = full_f1 = 0.0
    span_n = 0
    for r in dev:
        if r["yesno"]:
            continue
        span_n += 1
        a, _sc = rd._span(r["q"], r["gold_ev"])
        gold_f1 += _f1(a, r["ans"])
        out = rd.answer(r["q"], r["paras"], k=3, chain=False)        # full pipeline (support-select + span)
        full_f1 += _f1(out["answer"], r["ans"])
    rep = {"span_F1_on_gold_evidence": round(gold_f1 / max(1, span_n), 4),
           "full_pipeline_F1": round(full_f1 / max(1, span_n), 4), "span_n": span_n,
           "train_span": len(enc), "prev_full_F1": 0.077, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d3.1", json.dumps(rep))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"deliberator_d31_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
