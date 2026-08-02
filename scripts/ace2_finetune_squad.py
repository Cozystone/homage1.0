# -*- coding: utf-8 -*-
"""ACE2 Phase C (decisive) — fine-tune the RTD backbone on SQuAD 2.0 (joint answerability + span), then
measure answerability AUC + span F1 head-to-head vs ACE (0.68 / 0.53). The frozen probe was confounded
(ACE's backbone was SQuAD-trained, ACE2's only RTD-pretrained); THIS is the fair go/no-go for the bet.
model2 + data2, warm-started from ace2_backbone.pt. No pretrained weights. No LLM.

  python scripts/ace2_finetune_squad.py [nq] [epochs] [bs]
Gate: answerability AUC > 0.68 (beat ACE) AND span F1 >= 0.53.
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
import torch.nn as nn                                                 # noqa: E402
from packages.reasoning_vm.ace import data2 as D2                     # noqa: E402
from packages.reasoning_vm.ace.model2 import Ace2Encoder              # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
CKPT = REPO / "data" / "graph_scale" / "ace2_backbone.pt"
_ART = {"a", "an", "the"}


def _norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(p, g):
    p, g = _norm(p).split(), _norm(g).split()
    if not p or not g:
        return float(p == g)
    c = sum((Counter(p) & Counter(g)).values())
    return 0.0 if not c else 2 * (c / len(p)) * (c / len(g)) / (c / len(p) + c / len(g))


def _auc(y, s):
    o = np.argsort(s, kind="mergesort"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = float(y.sum()); n0 = float(len(y) - n1)
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else float("nan")


def main():
    t0 = time.time()
    # --ckpt/--out overrides (Plan B): fine-tune the MTL backbone WITHOUT clobbering the E9
    # artifacts (ace2_backbone.pt / ace2_squad.pt stay intact as the rollback pair).
    argv = list(sys.argv[1:])
    ckpt, out = CKPT, REPO / "data" / "graph_scale" / "ace2_squad.pt"
    if "--ckpt" in argv:
        i = argv.index("--ckpt"); ckpt = Path(argv[i + 1]); del argv[i:i + 2]
    if "--out" in argv:
        i = argv.index("--out"); out = Path(argv[i + 1]); del argv[i:i + 2]
    nq = int(argv[0]) if len(argv) > 0 else 40000
    epochs = int(argv[1]) if len(argv) > 1 else 3
    bs = int(argv[2]) if len(argv) > 2 else 24
    tok = D2.tokenizer()
    model = Ace2Encoder(tok.get_vocab_size()).to(DEV)
    if ckpt.exists():
        model.load_state_dict(torch.load(ckpt, map_location=DEV), strict=False)
        print(f"  warm-started from {ckpt.name}", flush=True)
    rows = [r for r in D2.load_squad("train")]
    random.Random(0).shuffle(rows); rows = rows[:nq]
    print(f"device {DEV} | {len(rows)} train | encoding…", flush=True)
    enc = [D2.encode(r["q"], r["ctx"], r["ans_start"], r["ans_text"]) for r in rows]
    for e, r in zip(enc, rows):
        e["answerable"] = r["answerable"]

    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, betas=(0.9, 0.98), weight_decay=0.01)
    steps = (len(enc) + bs - 1) // bs * epochs
    warm = max(1, steps // 25)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    bce = nn.BCEWithLogitsLoss(); ce = nn.CrossEntropyLoss()
    rng = np.random.default_rng(0); step = 0
    for ep in range(epochs):
        order = rng.permutation(len(enc)); model.train()
        for i in range(0, len(order), bs):
            batch = [enc[j] for j in order[i:i + bs]]
            b = D2.collate(batch, tok); b = {k: v.to(DEV) for k, v in b.items()}
            ans_y = torch.tensor([x["answerable"] for x in batch], dtype=torch.float32, device=DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                ans, start, end = model(b["ids"], b["seg"], b["feats"], b["pad"])
                loss = 2.0 * bce(ans, ans_y) + ce(start, b["start"]) + ce(end, b["end"])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 500 == 0:
                print(f"    step {step}/{steps} loss {loss.item():.3f} ({round(time.time()-t0,1)}s)", flush=True)
    torch.save(model.state_dict(), out)

    # eval: answerability AUC + span F1
    model.eval()
    dev = D2.load_squad("dev"); random.Random(1).shuffle(dev); dev = dev[:3000]
    p_ans, y, f1, span_n = [], [], 0.0, 0
    for i in range(0, len(dev), 64):
        chunk = dev[i:i + 64]
        b = D2.collate([D2.encode(r["q"], r["ctx"]) for r in chunk], tok)
        b = {k: v.to(DEV) for k, v in b.items()}
        with torch.no_grad(), torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
            ans, start, end = model(b["ids"], b["seg"], b["feats"], b["pad"])
        p_ans.extend(torch.sigmoid(ans.float()).cpu().numpy()); y.extend(int(r["answerable"]) for r in chunk)
        for j, r in enumerate(chunk):
            if not r["answerable"]:
                continue
            span_n += 1
            e = D2.encode(r["q"], r["ctx"]); off, plen, ch = e["p_off"], e["p_len"], e["p_char"]
            if not ch or plen == 0:
                continue
            s = start[j, off:off + plen].float().cpu().numpy(); en = end[j, off:off + plen].float().cpu().numpy()
            bi = int(np.argmax(s)); bj = bi + int(np.argmax(en[bi:bi + 30]))
            ans_txt = r["ctx"][ch[bi][0]:ch[min(bj, len(ch) - 1)][1]]
            f1 += _f1(ans_txt, r["golds"][0] if r["golds"] else "")
    auc = _auc(np.array(y), np.array(p_ans))
    rep = {"benchmark": "ACE2 fine-tuned SQuAD 2.0 (decisive vs ACE 0.68/0.53)",
           "answerability_AUC": round(float(auc), 4), "span_F1": round(f1 / max(1, span_n), 4),
           "ACE_AUC": 0.68, "ACE_span_F1": 0.53,
           "beats_ACE_auc": bool(auc > 0.68), "steps": step, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT ace2_finetune", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
