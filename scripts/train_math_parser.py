# -*- coding: utf-8 -*-
"""L2 v0 — . (GSM8K 0.014) '' 
 : →( )→ → →. = 
 (AlphaGeometry). GSM8K ( ).

 python scripts/train_math_parser.py [epochs]
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
DATA = REPO / "data" / "graph_scale" / "synthetic_math.jsonl"
DEV = "cuda" if torch.cuda.is_available() else "cpu"
VOCAB = 8000
_W = re.compile(r"[a-z%]+")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _feat(q: str):
    v = np.zeros(VOCAB, dtype=np.float32)
    for w in _W.findall(q.lower()):
        v[hash(w) % VOCAB] += 1.0
    return v


def _apply(op, a, b):
    return {"+": a + b, "-": a - b, "*": a * b, "/": (a / b if b else 0)}[op]


def _exec_template(t: int, nums: list[float]):
    """ (template) + ( ) · → ."""
    try:
        if t == 0: s = nums[0] + nums[1]; return s - nums[2]
        if t == 1: s = nums[0] * nums[1]; return s + nums[2]
        if t == 2: return nums[0] / nums[1]
        if t == 3: s = nums[0] - nums[1]; return s * nums[2]
        if t == 4: return nums[0] * nums[1] / 100        # base, pct
        if t == 5: s = nums[0] + nums[1]; return s / nums[2]
    except (IndexError, ZeroDivisionError):
        return None
    return None


class Parser(nn.Module):
    def __init__(self, n_tmpl=6):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(VOCAB, 256), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(256, 64), nn.GELU(), nn.Linear(64, n_tmpl))

    def forward(self, x):
        return self.net(x)


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    rng = np.random.default_rng(0); rng.shuffle(rows)
    nv = 4000; val, tr = rows[:nv], rows[nv:]
    Xtr = np.stack([_feat(r["question"]) for r in tr]); ytr = np.array([r["template"] for r in tr])
    Xv = np.stack([_feat(r["question"]) for r in val]); yv = np.array([r["template"] for r in val])
    print(f"device {DEV} | train {len(tr)} val {nv}", flush=True)
    m = Parser().to(DEV); opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4)
    ce = nn.CrossEntropyLoss()
    Xtr_t = torch.tensor(Xtr, device=DEV); ytr_t = torch.tensor(ytr, device=DEV)
    Xv_t = torch.tensor(Xv, device=DEV)
    bs = 512; t0 = time.time()
    for ep in range(epochs):
        m.train(); perm = rng.permutation(len(tr))
        for i in range(0, len(tr), bs):
            idx = perm[i:i + bs]
            loss = ce(m(Xtr_t[idx]), ytr_t[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            tmpl_acc = (m(Xv_t).argmax(1).cpu().numpy() == yv).mean()
        print(f"  ep{ep+1} tmpl_acc {tmpl_acc:.4f} ({round(time.time()-t0)}s)", flush=True)


    m.eval(); solved = 0
    with torch.no_grad():
        preds = m(Xv_t).argmax(1).cpu().numpy()
    for r, pt in zip(val, preds):
        nums = [float(x) for x in _NUM.findall(r["question"])]
        got = _exec_template(int(pt), nums)
        if got is not None and abs(got - r["answer"]) < 1e-4:
            solved += 1
    e2e = solved / nv
    rep = {"benchmark": "L2 math parser (in-distribution synthetic)", "val_template_acc": round(float(tmpl_acc), 4),
           "val_end2end_solve_acc": round(e2e, 4), "n_val": nv,
           "reading": "훈련 파서+커널 실행이 자기 분포를 푼다(휴리스틱 0.014 대비). GSM8K 전이=생성 다양성 바운드."}
    print("RESULT train_math_parser", json.dumps(rep, ensure_ascii=False))
    torch.save(m.state_dict(), REPO / "data" / "graph_scale" / "math_parser.pt")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
