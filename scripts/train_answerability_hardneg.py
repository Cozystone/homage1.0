# -*- coding: utf-8 -*-
"""TCT target 1 — train the answerability head on the mined HARD NEGATIVES. Warm-start the whole encoder
from ace_squad.pt (keeps the span head) and fine-tune with a BCE answerability objective over
(question, passage)->answerable where the negatives are on-topic-but-wrong (the boundary AUC 0.68 was
missing). Save to ace_squad_hn.pt (v1 preserved). The doubt_gate_eval then measures AUC head-to-head.

  python scripts/train_answerability_hardneg.py [epochs] [bs]
Gate to deploy: dev answerability AUC > 0.672 (v1) AND SQuAD span not wrecked.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import torch                                                          # noqa: E402
import torch.nn as nn                                                 # noqa: E402
from packages.reasoning_vm import learned_discriminator as LD        # noqa: E402
from packages.reasoning_vm.ace import data as D                      # noqa: E402
from packages.reasoning_vm.ace.model import AceEncoder               # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
DATA = REPO / "data" / "graph_scale" / "answerability_hardneg.jsonl"
OUT = REPO / "data" / "graph_scale" / "ace_squad_hn.pt"


def main():
    t0 = time.time()
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    rows = [json.loads(ln) for ln in DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"device {DEV} | {len(rows)} hard-neg examples", flush=True)
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    sq = REPO / "data" / "graph_scale" / "ace_squad.pt"
    if sq.exists():
        model.load_state_dict(torch.load(sq, map_location=DEV), strict=False)
        print("  warm-started from ace_squad.pt (keeps span head)", flush=True)
    import os
    freeze = os.getenv("ATANOR_FREEZE_BACKBONE") == "1"
    if freeze:                                            # train ONLY the answerability head → span head
        for n, p in model.named_parameters():             #   and its frozen backbone are untouched
            p.requires_grad = n.startswith("ans_head")
        print("  FROZEN backbone — training ans_head only (span preserved)", flush=True)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=(1e-3 if freeze else 2e-4), weight_decay=0.01)
    npos = sum(1 for r in rows if r["answerable"] == 1)
    pw = (len(rows) - npos) / max(1, npos)               # balance the hard-negative-heavy set
    bce = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pw, device=DEV))
    print(f"  pos_weight {pw:.2f} ({npos} pos / {len(rows)-npos} neg)", flush=True)
    steps = ((len(rows) + bs - 1) // bs) * epochs
    warm = max(1, steps // 25)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    rng = np.random.default_rng(0)
    step = 0
    for ep in range(epochs):
        order = rng.permutation(len(rows))
        model.train()
        for i in range(0, len(order), bs):
            batch = [rows[j] for j in order[i:i + bs]]
            enc = [D.encode(tok, b["q"], b["ctx"]) for b in batch]
            col = D.collate(enc, tok)
            col = {k: v.to(DEV) for k, v in col.items()}
            y = torch.tensor([float(b["answerable"]) for b in batch], device=DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                ans_logit, _s, _e = model(col["ids"], col["seg"], col["feats"], col["pad"])
                loss = bce(ans_logit, y)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 400 == 0:
                print(f"    step {step}/{steps} loss {loss.item():.4f} ({round(time.time()-t0,1)}s)", flush=True)
    torch.save(model.state_dict(), OUT)
    print(f"\nRESULT hardneg {json.dumps({'saved': OUT.name, 'steps': step, 'elapsed_s': round(time.time()-t0,1)})}")
    print("NEXT: ATANOR_SQUAD_CKPT=ace_squad_hn.pt python scripts/doubt_gate_eval.py 3000  # gate vs 0.672")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
