# -*- coding: utf-8 -*-
"""L1 v0 — (, )→ MCQ (No pretrained LLM).
 : - ** ?** MCQ (4 
 ) 0.25 = . = ACE2 .

 : ( ) + MLP → . [,3] CE.

 python scripts/train_mcq_judge.py [epochs] [data.jsonl]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import torch                                                    # noqa: E402
import torch.nn as nn                                           # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
VOCAB = 40000
_TOK = re.compile(r"[a-z0-9]+")


def _ids(text: str, n: int = 16) -> list[int]:
    toks = _TOK.findall(str(text).lower())[:n]
    return [(hash(t) % (VOCAB - 1)) + 1 for t in toks] or [0]


def _pad(seqs, n):
    a = np.zeros((len(seqs), n), dtype=np.int64)
    for i, s in enumerate(seqs):
        a[i, :len(s)] = s[:n]
    return a


class Judge(nn.Module):
    def __init__(self, d=128):
        super().__init__()
        self.emb = nn.EmbeddingBag(VOCAB, d, mode="mean", padding_idx=0)
        self.mlp = nn.Sequential(nn.Linear(4 * d, 256), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(256, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, q, o):                                    # q,o: (B, L) token ids
        qe, oe = self.emb(q), self.emb(o)
        feat = torch.cat([qe, oe, qe * oe, (qe - oe).abs()], dim=-1)
        return self.mlp(feat).squeeze(-1)                       # (B,)


def main():
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "graph_scale" / "graph_mcq.jsonl"
    rows = [json.loads(l) for l in data.read_text(encoding="utf-8").splitlines()]
    rng = np.random.default_rng(0); rng.shuffle(rows)
    n_val = min(2000, len(rows) // 5)
    val, tr = rows[:n_val], rows[n_val:]
    print(f"device {DEV} | train {len(tr)} | val {n_val}", flush=True)

    def batch(items):

        qs, os_, gold = [], [], []
        for r in items:
            opts = [r["gold"]] + r["distractors"][:3]
            for o in opts:
                qs.append(_ids(r["q"])); os_.append(_ids(o))
            gold.append(0)
        q = torch.tensor(_pad(qs, 16), device=DEV); o = torch.tensor(_pad(os_, 8), device=DEV)
        return q, o, torch.tensor(gold, device=DEV)

    model = Judge().to(DEV)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    ce = nn.CrossEntropyLoss()
    bs = 256; t0 = time.time()
    for ep in range(epochs):
        model.train(); rng.shuffle(tr); tot = 0.0
        for i in range(0, len(tr), bs):
            chunk = tr[i:i + bs]
            q, o, gold = batch(chunk)
            logits = model(q, o).view(len(chunk), 4)            # (B,4)
            loss = ce(logits, gold)
            opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item()

        model.eval()
        with torch.no_grad():
            q, o, gold = batch(val)
            acc = (model(q, o).view(n_val, 4).argmax(1) == 0).float().mean().item()
        print(f"  ep{ep+1} loss {tot/(len(tr)//bs+1):.3f} val_acc {acc:.4f} ({round(time.time()-t0)}s)", flush=True)

    rep = {"benchmark": "MCQ judge on graph hard-negatives", "val_mcq_acc": round(acc, 4),
           "random_baseline": 0.25, "n_train": len(tr), "n_val": n_val, "epochs": epochs,
           "reading": "val_acc >> 0.25 = 그래프 하드네거에 학습된 판별 신호 존재(진짜 레버). 정체=기각."}
    print("RESULT train_mcq_judge", json.dumps(rep, ensure_ascii=False))
    torch.save(model.state_dict(), REPO / "data" / "graph_scale" / "mcq_judge.pt")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
