# -*- coding: utf-8 -*-
"""ACE2 Plan B — multitask semantic pretraining (docs/ATANOR_e9_planb_and_self_model.md).

Root-cause of the E9 shortfall: token-level RTD on wiki, retrieval-frozen, sharpens local collocation
but not the SENTENCE-level, relational, RETRIEVAL semantics that answering needs. This trainer fixes
the objective, not the step count. Three objectives on ONE shared backbone (the thing that transfers):

  RTD  (aux)  — keep the cheap per-token real/replaced signal (helps local features).      [ELECTRA]
  B1  ICT     — Inverse Cloze Task: a random sentence is a pseudo-query, its surrounding passage is
                the positive; in-batch InfoNCE. From-scratch retriever pretraining, ZERO labels,
                No-LLM (ORQA/REALM/DPR lineage). Directly optimises the CLS sentence representation
                RTD neglects AND makes the encoder a retriever — attacking the retrieval-bound wall.
  B2  GRAPH   — graph-grounded alignment: (entity mention, verbalised 1-hop neighborhood) InfoNCE.
                Meaning as position relative to the CURATED graph — our unique lever. Activates when
                data/graph_scale/graph_pairs.jsonl exists (scripts/ace2_mine_graph_pairs.py); else
                skipped with a log. Its neighborhood contrastive is also the seed of B3 (relational
                supervision); a dedicated relation-classification head is the next extension (TODO).

Contrastive uses a script-local projection MLP on the backbone CLS (SimCLR-style; discarded at
fine-tune — only the backbone ships). Warm-starts from the E9 RTD backbone and saves to a SEPARATE
file so the RTD backbone stays intact as a rollback (always one safe place to fall back to). No
pretrained weights. No LLM.

  python scripts/ace2_pretrain_multitask.py [steps] [bs]      # STAGED — run after the E9 verdict frees the GPU
Verdict (unchanged, sealed): re-run scripts/ace2_finetune_squad.py on ace2_backbone_mtl.pt, then the
frozen scripts/diagnose_semantic_oracle.py. Gate stays ORACLE >= 0.30 / AUC > 0.68.
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

import torch                                                              # noqa: E402
import torch.nn as nn                                                     # noqa: E402
import torch.nn.functional as F                                          # noqa: E402
from packages.reasoning_vm.ace.model2 import Ace2Encoder, count_params   # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
GRAPH_PAIRS = REPO / "data" / "graph_scale" / "graph_pairs.jsonl"
WARM = REPO / "data" / "graph_scale" / "ace2_backbone.pt"                 # E9 RTD backbone (read-only)
OUT = REPO / "data" / "graph_scale" / "ace2_backbone_mtl.pt"             # separate — RTD backbone preserved
PAD, CLS, SEP, MASK = 0, 1, 2, 3
MASK_FRAC = 0.25
SEQ, Q_LEN, E_LEN = 128, 48, 128                                          # RTD packed len; ICT query/evidence
TEMP = 0.05
_SENT = re.compile(r"(?<=[.!?])\s+")


class Generator(nn.Module):
    """Small G for RTD (identical role to ace2_pretrain_rtd.Generator); co-trained, then discarded."""
    def __init__(self, vocab, d=192, layers=4, heads=6, ffn=512):
        super().__init__()
        self.enc = Ace2Encoder(vocab, d_model=d, layers=layers, heads=heads, ffn=ffn, max_len=256)
        self.proj = nn.Linear(d, vocab)

    def forward(self, ids, seg, pad, mask_pos):
        h = self.enc._backbone(ids, seg, None, pad)
        return self.proj(h[mask_pos[:, 0], mask_pos[:, 1]])


def _encode(tok, text, maxlen):
    """text -> [CLS] + ids (truncated), right-padded to maxlen. Returns int64 array."""
    ids = tok.encode(text).ids[: maxlen - 1]
    row = np.full(maxlen, PAD, np.int64)
    row[0] = CLS
    row[1 : 1 + len(ids)] = ids
    return row


def _stream_passages(limit):
    """Yield passages (text) with >=2 sentences, for ICT + RTD. Loops the file if under limit."""
    out = []
    while len(out) < limit:
        with open(PASSAGES, encoding="utf-8") as fh:
            for line in fh:
                t = line.find("\t")
                text = (line[t + 1:] if t >= 0 else line).strip()
                if len(text) < 80:
                    continue
                sents = [s for s in _SENT.split(text) if len(s) > 15]
                if len(sents) >= 2:
                    out.append(sents)
                    if len(out) >= limit:
                        return out
    return out


def _load_graph_pairs():
    if not GRAPH_PAIRS.exists():
        return None
    pairs = []
    with open(GRAPH_PAIRS, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
                if d.get("mention") and d.get("neighborhood"):
                    pairs.append((d["mention"], d["neighborhood"]))
            except json.JSONDecodeError:
                continue
    return pairs or None


def _pool(D, ids, proj):
    seg = torch.ones_like(ids)
    pad = ids.eq(PAD)
    cls = D._backbone(ids, seg, None, pad)[:, 0]        # (B, d)  shared backbone CLS
    return F.normalize(proj(cls), dim=-1)               # (B, p)


def _info_nce(a, b, ce):
    """Symmetric in-batch InfoNCE between aligned rows of a,b (both L2-normalised)."""
    logits = (a @ b.t()) / TEMP                          # (B, B)
    labels = torch.arange(a.shape[0], device=a.device)
    return 0.5 * (ce(logits, labels) + ce(logits.t(), labels))


def main() -> int:
    from tokenizers import Tokenizer
    t0 = time.time()
    steps_cap = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 48
    tok = Tokenizer.from_file(str(TOKJSON))
    V = tok.get_vocab_size()

    need = (steps_cap * bs + bs) if steps_cap > 0 else 1_500_000
    print(f"device {DEV} | vocab {V} | streaming ~{need:,} passages for ICT+RTD…", flush=True)
    passages = _stream_passages(need)
    gpairs = _load_graph_pairs()
    print(f"  {len(passages):,} passages | graph_pairs {'—' if gpairs is None else format(len(gpairs), ',')}"
          f"  (B2 {'OFF' if gpairs is None else 'ON'})  ({round(time.time()-t0,1)}s)", flush=True)

    D = Ace2Encoder(V).to(DEV)
    if WARM.exists():
        D.load_state_dict(torch.load(WARM, map_location=DEV)); print(f"  warm-started from {WARM.name}", flush=True)
    G = Generator(V).to(DEV)
    proj = nn.Sequential(nn.Linear(384, 384), nn.GELU(), nn.Linear(384, 256)).to(DEV)   # contrastive head
    print(f"  D {count_params(D)/1e6:.1f}M | G {count_params(G)/1e6:.1f}M | proj {count_params(proj)/1e6:.2f}M",
          flush=True)

    params = list(D.parameters()) + list(G.parameters()) + list(proj.parameters())
    opt = torch.optim.AdamW(params, lr=3e-4, betas=(0.9, 0.98), weight_decay=0.01)
    total = steps_cap if steps_cap > 0 else len(passages) // bs
    warm = max(1, total // 30)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, total - warm)))))
    ce = nn.CrossEntropyLoss()
    bce = nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(0)
    order = rng.permutation(len(passages))
    HARDCAP_S = 24 * 3600
    print(f"  total steps {total:,}", flush=True)

    step = 0
    while step < total:
        i = (step * bs) % max(1, len(order) - bs)
        if step > 0 and i < bs:
            order = rng.permutation(len(passages))
        idx = order[i:i + bs]
        sample = [passages[j] for j in idx]

        # --- assemble the three objectives' inputs ---
        rtd_rows, q_rows, e_rows = [], [], []
        for sents in sample:
            qi = rng.integers(len(sents))
            q_rows.append(_encode(tok, sents[qi], Q_LEN))
            e_rows.append(_encode(tok, " ".join(s for k, s in enumerate(sents) if k != qi), E_LEN))
            packed = tok.encode(" ".join(sents)).ids[: SEQ - 1]
            row = np.full(SEQ, PAD, np.int64); row[0] = CLS; row[1:1 + len(packed)] = packed
            rtd_rows.append(row)
        rtd = torch.from_numpy(np.stack(rtd_rows)).to(DEV)
        q = torch.from_numpy(np.stack(q_rows)).to(DEV)
        e = torch.from_numpy(np.stack(e_rows)).to(DEV)

        with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
            # RTD (aux)
            seg = torch.ones_like(rtd); pad = rtd.eq(PAD)
            mask = (torch.rand_like(rtd, dtype=torch.float) < MASK_FRAC) & (rtd > MASK)
            mp = mask.nonzero(as_tuple=False)
            if len(mp) == 0:
                step += 1; continue
            g_logits = G(rtd.masked_fill(mask, MASK), seg, pad, mp)
            l_g = ce(g_logits, rtd[mp[:, 0], mp[:, 1]])
            with torch.no_grad():
                samp = torch.multinomial(torch.softmax(g_logits.float(), -1), 1).squeeze(-1)
            corrupt = rtd.clone(); corrupt[mp[:, 0], mp[:, 1]] = samp
            replaced = (corrupt != rtd).float()
            l_d = bce(D.discriminate(corrupt, seg, pad), replaced)
            l_rtd = l_g + 50.0 * l_d

            # B1 ICT (pseudo-query <-> passage)
            l_ict = _info_nce(_pool(D, q, proj), _pool(D, e, proj), ce)

            # B2 graph-grounded (mention <-> neighborhood), if available
            l_graph = torch.zeros((), device=DEV)
            if gpairs is not None:
                gi = rng.integers(0, len(gpairs), size=bs)
                m = torch.from_numpy(np.stack([_encode(tok, gpairs[k][0], Q_LEN) for k in gi])).to(DEV)
                nb = torch.from_numpy(np.stack([_encode(tok, gpairs[k][1], E_LEN) for k in gi])).to(DEV)
                l_graph = _info_nce(_pool(D, m, proj), _pool(D, nb, proj), ce)

            loss = l_rtd + l_ict + l_graph

        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step(); sched.step(); step += 1

        if step % 200 == 0:
            el = time.time() - t0
            print(f"    step {step}/{total} L_rtd {l_rtd.item():.3f} L_ict {l_ict.item():.3f} "
                  f"L_graph {float(l_graph):.3f} ({round(el,1)}s)", flush=True)
        if step % 5000 == 0:
            torch.save(D.state_dict(), OUT)
        if time.time() - t0 > HARDCAP_S:
            print("  24h hard cap — stopping", flush=True); break

    torch.save(D.state_dict(), OUT)
    print(f"\nRESULT ace2_mtl {json.dumps({'saved': OUT.name, 'steps': step, 'passages': len(passages), 'b2': gpairs is not None, 'elapsed_s': round(time.time()-t0, 1)})}",
          flush=True)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
