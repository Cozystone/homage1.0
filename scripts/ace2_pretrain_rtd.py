# -*- coding: utf-8 -*-
"""ACE2 Phase B — ELECTRA replaced-token-detection pretraining. A small generator G (co-trained from
scratch, then discarded) masks 25% of tokens and predicts them; we sample replacements from G and the
discriminator D (the full ACE2 backbone) learns to flag, at EVERY position, real-vs-replaced. RTD gives a
learning signal on all tokens (3-7x MLM efficiency) and the discrimination skill is homologous to
answerability — exactly our wall. loss = L_G + 50·L_D. No pretrained weights (G is ours). No LLM.

  python scripts/ace2_pretrain_rtd.py [steps] [bs] [seq]     # steps<=0 -> full 24h-capped run
Probe kill-gates (design): at 3h frozen-backbone ans-probe AUC>=0.62, at 8h>=0.68, else abort cheap.
Saves: data/graph_scale/ace2_backbone.pt  (discriminator backbone, for the fine-tune ladder)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import torch                                                          # noqa: E402
import torch.nn as nn                                                 # noqa: E402
from packages.reasoning_vm.ace.model2 import Ace2Encoder, count_params   # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "ace2_backbone.pt"
PAD, CLS, SEP, MASK = 0, 1, 2, 3
MASK_FRAC = 0.25


class Generator(nn.Module):
    """Small G: shallow ACE2 + a masked-positions-only vocab projection (OOM-safe)."""
    def __init__(self, vocab, d=192, layers=4, heads=6, ffn=512):
        super().__init__()
        self.enc = Ace2Encoder(vocab, d_model=d, layers=layers, heads=heads, ffn=ffn, max_len=256)
        self.proj = nn.Linear(d, vocab)

    def forward(self, ids, seg, pad, mask_pos):
        h = self.enc._backbone(ids, seg, None, pad)          # (B,L,d)
        return self.proj(h[mask_pos[:, 0], mask_pos[:, 1]])  # (M, vocab)


def _stream(tok, seq, limit_seqs):
    """Passages → packed BPE id sequences of length `seq` (Cramming-style packing)."""
    buf, out = [], []
    with open(PASSAGES, encoding="utf-8") as fh:
        for line in fh:
            t = line.find("\t")
            text = (line[t + 1:] if t >= 0 else line).strip()
            if len(text) < 40:
                continue
            buf.extend(tok.encode(text).ids)
            buf.append(SEP)
            while len(buf) >= seq:
                out.append(np.array(buf[:seq], np.int64)); buf = buf[seq:]
                if len(out) >= limit_seqs:
                    return out
    return out


def main():
    from tokenizers import Tokenizer
    t0 = time.time()
    steps_cap = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    seq = int(sys.argv[3]) if len(sys.argv) > 3 else 128
    tok = Tokenizer.from_file(str(TOKJSON))
    V = tok.get_vocab_size()
    # E9 data-plumbing fix (2026-07-18): the in-RAM buffer capped a "full" run at ~3M seqs =
    # 384M tokens — 43% of the corpus seen once, vs the design's 0.9B×2-3 epochs — and int64
    # for a 16k vocab wastes 4× RAM. If the one-time uint16 pack exists (ace2_pack_corpus.py),
    # memmap it: full corpus, true epochs, ~0 RAM. Hyperparameters unchanged — plumbing only.
    pack_bin = REPO / "data" / "graph_scale" / "ace2_pack" / "tokens_u16.bin"
    mm, n_win = None, 0
    if pack_bin.exists():
        mm = np.memmap(pack_bin, dtype=np.uint16, mode="r")
        n_win = len(mm) // seq
        print(f"device {DEV} | vocab {V} | pack {len(mm):,} tokens → {n_win:,} windows (seq {seq})",
              flush=True)
        data = None
    else:
        MAX_BUF = int(os.getenv("ATANOR_RTD_MAXBUF", "1500000"))  # bound RAM; longer runs reuse (≤4 epochs)
        n_seqs = min(steps_cap * bs + bs, MAX_BUF) if steps_cap > 0 else 3_000_000
        print(f"device {DEV} | vocab {V} | streaming ~{n_seqs} packed seqs (seq {seq})…", flush=True)
        data = _stream(tok, seq, n_seqs)
        print(f"  {len(data)} sequences ({round(time.time()-t0,1)}s)", flush=True)

    D = Ace2Encoder(V).to(DEV)
    G = Generator(V).to(DEV)
    print(f"  D {count_params(D)/1e6:.1f}M | G {count_params(G)/1e6:.1f}M", flush=True)
    opt = torch.optim.AdamW(list(D.parameters()) + list(G.parameters()), lr=5e-4, betas=(0.9, 0.98),
                            weight_decay=0.01)
    if steps_cap > 0:
        total = steps_cap
    elif mm is not None:                                # design budget: 2.5 epochs over the pack
        total = int(float(os.getenv("ATANOR_RTD_EPOCHS", "2.5")) * n_win / bs)
    else:
        total = len(data) // bs
    print(f"  total steps {total:,} (~{total * bs * seq / 1e9:.2f}B tokens)", flush=True)
    warm = max(1, total // 30)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, total - warm)))))
    ce = nn.CrossEntropyLoss()
    bce = nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(0)
    HARDCAP_S = 24 * 3600
    step = 0
    if mm is not None:
        order = rng.permutation(n_win)                  # epoch permutation over pack windows
    else:
        order = rng.permutation(len(data))
    while step < total:
        if mm is not None:
            i = (step * bs) % max(1, len(order) - bs)
            if step > 0 and i < bs:                     # wrapped → new epoch, reshuffle
                order = rng.permutation(n_win)
            ws = order[i:i + bs]
            batch = np.stack([np.asarray(mm[w * seq:(w + 1) * seq], dtype=np.int64) for w in ws])
        else:
            i = (step * bs) % max(1, len(order) - bs)
            batch = np.stack([data[order[j]] for j in range(i, i + bs)])
        ids = torch.from_numpy(batch).to(DEV)
        seg = torch.ones_like(ids)
        pad = torch.zeros_like(ids, dtype=torch.bool)
        # 1) mask 25% (not specials) → G predicts originals
        mask = (torch.rand_like(ids, dtype=torch.float) < MASK_FRAC) & (ids > MASK)
        mp = mask.nonzero(as_tuple=False)
        if len(mp) == 0:
            step += 1; continue
        masked_ids = ids.masked_fill(mask, MASK)
        with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
            g_logits = G(masked_ids, seg, pad, mp)                 # (M, V)
            orig = ids[mp[:, 0], mp[:, 1]]
            lg = ce(g_logits, orig)
            # 2) sample replacements from G → corrupted input
            with torch.no_grad():
                samp = torch.multinomial(torch.softmax(g_logits.float(), -1), 1).squeeze(-1)
            corrupt = ids.clone()
            corrupt[mp[:, 0], mp[:, 1]] = samp
            replaced = (corrupt != ids).float()                    # RTD label: 1 = replaced
            # 3) D flags real/replaced at every token
            d_logits = D.discriminate(corrupt, seg, pad)
            ld = bce(d_logits, replaced)
            loss = lg + 50.0 * ld
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(list(D.parameters()) + list(G.parameters()), 1.0)
        opt.step(); sched.step(); step += 1
        if step % 200 == 0:
            with torch.no_grad():
                dacc = ((d_logits > 0).float() == replaced).float().mean().item()
            el = time.time() - t0
            print(f"    step {step}/{total} L_G {lg.item():.3f} L_D {ld.item():.4f} D_acc {dacc:.3f} "
                  f"({round(el,1)}s, {step * bs * seq / max(1, el) / 1e3:.0f}k tok/s)", flush=True)
        if step % 5000 == 0:
            torch.save(D.state_dict(), OUT)             # probe target (ace2_probe.py reads OUT)
        if step % 25000 == 0:                           # rollback points for the 8h run
            torch.save(D.state_dict(), OUT.with_name(f"ace2_backbone_s{step}.pt"))
        if time.time() - t0 > HARDCAP_S:
            print("  24h hard cap reached — stopping", flush=True)
            break
    torch.save(D.state_dict(), OUT)
    n_data = n_win if mm is not None else len(data)
    print(f"\nRESULT ace2_rtd {json.dumps({'saved': OUT.name, 'steps': step, 'seqs': n_data, 'pack': bool(mm is not None), 'elapsed_s': round(time.time()-t0,1)})}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
