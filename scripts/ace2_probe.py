# -*- coding: utf-8 -*-
"""ACE2 probe kill-gate — how good is the RTD backbone SO FAR at answerability, without fine-tuning? Freeze
the current ace2_backbone.pt, extract the CLS vector for SQuAD (question, passage) pairs, fit a tiny
logistic probe (frozen features), and report held-out AUC. Design gates: >=0.62 at 3h, >=0.68 at 8h — else
kill the pretrain cheap (the 0-8 blind lesson: fail fast). No fine-tuning, no GPU spend beyond a forward pass.

  python scripts/ace2_probe.py [n]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
CKPT = REPO / "data" / "graph_scale" / "ace2_backbone.pt"
CLS, SEP = 1, 2


def _auc(y, s):
    order = np.argsort(s, kind="mergesort")
    r = np.empty(len(s)); r[order] = np.arange(1, len(s) + 1)
    n1 = float(y.sum()); n0 = float(len(y) - n1)
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else float("nan")


def main():
    import torch
    from tokenizers import Tokenizer
    from packages.reasoning_vm.ace import data as D
    from packages.reasoning_vm.ace.model2 import Ace2Encoder
    from packages.reasoning_vm.deliberator.doubt_gate import _Logistic
    t0 = time.time()
    # --ckpt <path>: probe a COPY instead of the live ace2_backbone.pt — the trainer overwrites
    # it every 5k steps and torch.save is not atomic, so probing mid-run reads a torn file.
    global CKPT
    raw_ckpt = None
    if "--ckpt" in sys.argv:
        raw_ckpt = sys.argv[sys.argv.index("--ckpt") + 1]
        CKPT = Path(raw_ckpt)
    pos = [a for a in sys.argv[1:] if not a.startswith("--") and a != raw_ckpt]
    n = int(pos[0]) if pos else 3000
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = Tokenizer.from_file(str(TOKJSON))
    model = Ace2Encoder(tok.get_vocab_size()).to(dev).eval()
    if CKPT.exists():
        model.load_state_dict(torch.load(CKPT, map_location=dev), strict=False)
    rows = D.load_squad("dev")
    import random
    random.Random(0).shuffle(rows)
    rows = rows[:n]

    def cls_batch(batch):
        enc = []
        for r in batch:
            qi = tok.encode(r["q"]).ids[:60]
            pi = tok.encode(r["ctx"]).ids[:180]
            ids = [CLS] + qi + [SEP] + pi + [SEP]
            seg = [0] * (len(qi) + 2) + [1] * (len(pi) + 1)
            enc.append((ids, seg))
        L = max(len(e[0]) for e in enc)
        I = np.zeros((len(enc), L), np.int64); S = np.zeros((len(enc), L), np.int64)
        P = np.ones((len(enc), L), bool)
        for i, (ids, seg) in enumerate(enc):
            I[i, :len(ids)] = ids; S[i, :len(seg)] = seg; P[i, :len(ids)] = False
        I = torch.from_numpy(I).to(dev); S = torch.from_numpy(S).to(dev); P = torch.from_numpy(P).to(dev)
        with torch.no_grad(), torch.autocast(dev, dtype=torch.bfloat16, enabled=(dev == "cuda")):
            hb = model._backbone(I, S, None, P).float()        # (B,L,d)
        cls = hb[:, 0]
        m = (~P).float().unsqueeze(-1)
        mean = (hb * m).sum(1) / m.sum(1).clamp(min=1)          # masked mean-pool
        return cls.cpu().numpy(), mean.cpu().numpy()

    Xc, Xm, y = [], [], []
    for i in range(0, len(rows), 128):
        c, m = cls_batch(rows[i:i + 128])
        Xc.append(c); Xm.append(m)
        y.extend(int(r["answerable"]) for r in rows[i:i + 128])
    Xc = np.concatenate(Xc, 0); Xm = np.concatenate(Xm, 0); y = np.array(y)
    half = len(y) // 2

    def _probe(X):
        lr = _Logistic().fit(X[:half], y[:half])
        return round(float(_auc(y[half:], lr.prob(X[half:]))), 4)
    auc_cls, auc_mean = _probe(Xc), _probe(Xm)
    auc = max(auc_cls, auc_mean)
    rep = {"probe": "ACE2 frozen-backbone answerability AUC", "n": len(y),
           "AUC_cls": auc_cls, "AUC_meanpool": auc_mean, "AUC": auc,
           "gate_3h>=0.62": bool(auc >= 0.62), "gate_8h>=0.68": bool(auc >= 0.68),
           "ckpt_exists": CKPT.exists(), "elapsed_s": round(time.time() - t0, 1)}
    print("RESULT ace2_probe", json.dumps(rep))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
