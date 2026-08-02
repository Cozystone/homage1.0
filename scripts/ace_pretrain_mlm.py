# -*- coding: utf-8 -*-
"""ACE M3 — self-supervised MLM pretraining on OUR full-enwiki harvest (No external weights, ever).

Masked-word prediction over the ACE backbone: 15% of tokens masked, model predicts the original id.
This is the span-quality fuel the SQuAD gates asked for — the encoder learns English structure from
OUR 7M-passage substrate before any supervised head. Compressed for the 2-day sprint: 2M passages,
seq 128, bf16, GPU-shared (bs32 + expandable segments).

  python scripts/ace_pretrain_mlm.py [n_passages] [epochs] [bs]
Saves: data/graph_scale/ace_mlm_backbone.pt  (load with strict=False for downstream warm-start)
"""
from __future__ import annotations

import json
import random
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
from packages.reasoning_vm.ace.model import AceEncoder, count_params  # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "ace_mlm_backbone.pt"
SEQ = 128
MASK_ID = 3            # reuse UNK slot as [MASK]
MASK_FRAC = 0.15


class MLMHead(nn.Module):
    def __init__(self, enc: AceEncoder, n_ids: int, d_model: int = 256):
        super().__init__()
        self.enc = enc
        self.proj = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.LayerNorm(d_model))
        self.out = nn.Linear(d_model, n_ids)

    def forward(self, ids, seg, feats, pad, mask_pos):
        """Project ONLY the masked positions through the vocab layer (mask_pos: (M,2) [batch,seq] idx)
        — the standard memory trick; full-length vocab logits OOM on a shared GPU."""
        h = self.enc._backbone(ids, seg, feats, pad)                  # (B, L, d)
        sel = h[mask_pos[:, 0], mask_pos[:, 1]]                       # (M, d)
        return self.out(self.proj(sel))                               # (M, V)


def _stream_ids(tok, limit: int, offset: int = 0):
    """Passage → id sequence (seq≤SEQ). One pass over the TSV; skips short lines. `offset` skips that many
    VALID passages first, so a continuation run can see FRESH data beyond the original pretraining slice."""
    out = []
    seen = 0
    import re
    word = re.compile(r"[A-Za-z0-9]+")
    with open(PASSAGES, encoding="utf-8") as fh:
        for line in fh:
            t = line.find("\t")
            if t < 0:
                continue
            ws = word.findall(line[t + 1:])[:SEQ]
            if len(ws) < 24:
                continue
            seen += 1
            if seen <= offset:
                continue
            out.append(np.array([tok.wid(w) for w in ws], np.int64))
            if len(out) >= limit:
                break
    return out


def main():
    import os
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    bs = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    offset = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    cont = os.getenv("ATANOR_MLM_CONTINUE") == "1"           # warm-start the whole backbone, save versioned
    out_path = REPO / "data" / "graph_scale" / ("ace_mlm_backbone_v2.pt" if cont else "ace_mlm_backbone.pt")
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    print(f"device {DEV} | streaming {n} passages (offset {offset}, continue={cont})…", flush=True)
    seqs = _stream_ids(tok, n, offset)
    print(f"  {len(seqs)} sequences ({round(time.time()-t0,1)}s)", flush=True)

    enc = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    if cont and OUT.exists():                                # CONTINUATION: keep the existing backbone
        enc.load_state_dict(torch.load(OUT, map_location=DEV), strict=False)
        print("  warm-started from ace_mlm_backbone.pt (continuation)", flush=True)
    model = MLMHead(enc, tok.n_ids).to(DEV)
    print(f"  params {count_params(model)/1e6:.1f}M | MLM training→ {out_path.name}…", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=(1e-4 if cont else 4e-4), weight_decay=0.01)
    steps = ((len(seqs) + bs - 1) // bs) * epochs
    warm = max(1, steps // 50)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    rng = np.random.default_rng(0)
    step = 0
    for ep in range(epochs):
        order = rng.permutation(len(seqs))
        for i in range(0, len(order), bs):
            batch = [seqs[j] for j in order[i:i + bs]]
            L = max(len(s) for s in batch)
            ids = np.zeros((len(batch), L), np.int64)
            pad = np.ones((len(batch), L), bool)
            labels = np.full((len(batch), L), -100, np.int64)
            for bi, s in enumerate(batch):
                ids[bi, :len(s)] = s
                pad[bi, :len(s)] = False
                m = rng.random(len(s)) < MASK_FRAC
                labels[bi, :len(s)][m] = s[m]
                ids[bi, :len(s)][m] = MASK_ID
            mp = np.argwhere(labels != -100)
            if len(mp) == 0:
                continue
            tids = torch.from_numpy(ids).to(DEV)
            tpad = torch.from_numpy(pad).to(DEV)
            seg = torch.ones_like(tids)
            feats = torch.zeros((*tids.shape, D.NFEAT), dtype=torch.float32, device=DEV)
            tmp = torch.from_numpy(mp).to(DEV)
            tgt = torch.from_numpy(labels[mp[:, 0], mp[:, 1]]).to(DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                logits = model(tids, seg, feats, tpad, tmp)           # (M, V) — masked positions only
                loss = ce(logits, tgt)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 500 == 0:
                print(f"    step {step}/{steps} mlm_loss {loss.item():.4f} "
                      f"({round(time.time()-t0,1)}s)", flush=True)
            if step % 5000 == 0:
                torch.save(enc.state_dict(), out_path)      # periodic checkpoint (backbone only)
    torch.save(enc.state_dict(), out_path)
    ppl = float(np.exp(min(20.0, loss.item())))
    print(f"\nRESULT m3 {json.dumps({'final_mlm_loss': round(loss.item(),4), 'approx_ppl': round(ppl,1), 'sequences': len(seqs), 'steps': step, 'elapsed_s': round(time.time()-t0,1)})}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
