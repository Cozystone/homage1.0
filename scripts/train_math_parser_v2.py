# -*- coding: utf-8 -*-
"""L2 v2 — → ( ). (base/+/-/*//) .
'gave away N'→-, 'N more'→+, 'N times'→*, 'into N groups'→/ GSM8K → .
in-dist + **GSM8K ** (: ). =(0).

 python scripts/train_math_parser_v2.py [epochs]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "graph_scale" / "synthetic_math_v2.jsonl"
GSM = REPO / "data" / "benchmarks" / "gsm8k" / "test.jsonl"
DEV = "cuda" if torch.cuda.is_available() else "cpu"
VOCAB = 12000
WIN = 5
LABELS = ["base", "+", "-", "*", "/"]
_TOKEN = re.compile(r"[A-Za-z%$]+|\d+(?:\.\d+)?|[.,!?]")
_NUMTOK = re.compile(r"^\d+(?:\.\d+)?$")


def _tokens(q: str):
    return _TOKEN.findall(q.replace(",", ""))


def _num_contexts(q: str):
    """ → [(value, context_feature_ids, position_frac), ...] ."""
    toks = _tokens(q)
    out = []
    for i, t in enumerate(toks):
        if _NUMTOK.match(t):
            ctx = toks[max(0, i - WIN):i] + ["<N>"] + toks[i + 1:i + 1 + WIN]
            ids = [hash(w.lower()) % VOCAB for w in ctx]
            out.append((float(t), ids, i / max(1, len(toks))))
    return out


def _bag(ids):
    v = np.zeros(VOCAB, dtype=np.float32)
    for x in ids:
        v[x] += 1.0
    return v


class NumOp(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(VOCAB + 1, 256), nn.GELU(), nn.Dropout(0.15),
                                 nn.Linear(256, 64), nn.GELU(), nn.Linear(64, len(LABELS)))

    def forward(self, x):
        return self.net(x)


def _feat_row(ids, pos):
    return np.concatenate([_bag(ids), [pos]]).astype(np.float32)


def _fold(nums, labs):
    if not nums or labs[0] != "base":
        return None
    acc = nums[0]
    for lab, v in zip(labs[1:], nums[1:]):
        if lab == "+": acc += v
        elif lab == "-": acc -= v
        elif lab == "*": acc *= v
        elif lab == "/": acc = acc / v if v else None
        if acc is None:
            return None
    return acc


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    rng = np.random.default_rng(0); rng.shuffle(rows)
    nv = 4000; val, tr = rows[:nv], rows[nv:]


    def rows_to_xy(rs):
        X, Y = [], []
        for r in rs:
            ctxs = _num_contexts(r["question"])
            if len(ctxs) != len(r["numbers"]):
                continue
            for (v, ids, pos), lab in zip(ctxs, r["labels"]):
                X.append(_feat_row(ids, pos)); Y.append(LABELS.index(lab))
        return np.stack(X), np.array(Y)

    Xtr, Ytr = rows_to_xy(tr)
    print(f"device {DEV} | train nums {len(Xtr)} | val prob {nv}", flush=True)
    m = NumOp().to(DEV); opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4)
    ce = nn.CrossEntropyLoss()
    Xt = torch.tensor(Xtr, device=DEV); Yt = torch.tensor(Ytr, device=DEV)
    bs = 1024; t0 = time.time()
    for ep in range(epochs):
        m.train(); perm = rng.permutation(len(Xtr))
        for i in range(0, len(Xtr), bs):
            idx = perm[i:i + bs]
            loss = ce(m(Xt[idx]), Yt[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        print(f"  ep{ep+1} loss {loss.item():.3f} ({round(time.time()-t0)}s)", flush=True)

    m.eval()

    def solve(q):
        ctxs = _num_contexts(q)
        if not ctxs:
            return None
        feats = torch.tensor(np.stack([_feat_row(ids, pos) for _v, ids, pos in ctxs]), device=DEV)
        with torch.no_grad():
            labs = [LABELS[i] for i in m(feats).argmax(1).cpu().numpy()]
        if labs[0] != "base":
            labs[0] = "base"
        return _fold([v for v, _i, _p in ctxs], labs)


    ind = sum(1 for r in val if (s := solve(r["question"])) is not None and abs(s - r["answer"]) < 1e-4)

    g_rows = [json.loads(l) for l in GSM.read_text(encoding="utf-8").splitlines()]
    def gold(a):
        mm = re.search(r"####\s*([-\d.,]+)", a); return float(mm.group(1).replace(",", "")) if mm else None
    gc = gt = 0
    for r in g_rows:
        gv = gold(r["answer"])
        if gv is None: continue
        gt += 1
        s = solve(r["question"])
        if s is not None and abs(s - gv) < 1e-4:
            gc += 1
    rep = {"benchmark": "L2 math parser v2 (per-number op classify)",
           "in_dist_solve": round(ind / nv, 4),
           "GSM8K_transfer": round(gc / gt, 4), "gsm8k_n": gt,
           "vs_heuristic_v0": 0.014,
           "reading": "GSM8K_transfer > 0.014 = 전이 시작. 숫자-문맥 신호가 실 문제로 넘어감."}
    print("RESULT train_math_parser_v2", json.dumps(rep, ensure_ascii=False))
    torch.save(m.state_dict(), REPO / "data" / "graph_scale" / "math_parser_v2.pt")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
