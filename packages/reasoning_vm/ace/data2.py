# -*- coding: utf-8 -*-
"""ACE2 QA data pipeline — byte-BPE encode/collate mirroring ace/data.py's interface so the fine-tune
ladder + eval harness reuse unchanged (swap `data` → `data2`). Span targets come from BPE offset overlap
(the Phase-A-validated, char-exact alignment). Hand features retired: `feats` is a zero channel kept only
for call-signature compatibility with model2 (which ignores it). No LLM."""
from __future__ import annotations

from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
PAD, CLS, SEP, MASK, UNK = 0, 1, 2, 3, 4
Q_MAX, P_MAX = 48, 178
SEQ_MAX = 1 + Q_MAX + 1 + P_MAX + 1
NFEAT = 1                                                   # dummy channel (features retired)

_TOK = None


def tokenizer():
    global _TOK
    if _TOK is None:
        from tokenizers import Tokenizer
        _TOK = Tokenizer.from_file(str(TOKJSON))
    return _TOK


def encode(question: str, context: str, ans_start: int = -1, ans_text: str = ""):
    """→ ids/seg/feats + start/end token targets + p_off/p_len/p_char (char spans for decode)."""
    tok = tokenizer()
    qe = tok.encode(question)
    pe = tok.encode(context)
    q_ids = qe.ids[:Q_MAX]
    p_ids = pe.ids[:P_MAX]
    p_off_char = pe.offsets[:P_MAX]                         # char span of each kept passage token

    ids = [CLS] + q_ids + [SEP] + p_ids + [SEP]
    seg = [0] * (len(q_ids) + 2) + [1] * (len(p_ids) + 1)
    p_off = len(q_ids) + 2                                  # first passage token position in the sequence

    start_t = end_t = 0
    has_span = 0
    if ans_start >= 0 and ans_text:
        a0, a1 = ans_start, ans_start + len(ans_text)
        hit = [j for j, (s, e) in enumerate(p_off_char) if s < a1 and e > a0]
        if hit:
            start_t = p_off + hit[0]
            end_t = p_off + hit[-1]
            has_span = 1
    return {"ids": np.array(ids, np.int64), "seg": np.array(seg, np.int64),
            "feats": np.zeros((len(ids), NFEAT), np.float32), "start": start_t, "end": end_t,
            "has_span": has_span, "p_off": p_off, "p_len": len(p_ids), "p_char": list(p_off_char)}


def collate(batch, tok=None):
    import torch
    L = max(len(b["ids"]) for b in batch)
    n = len(batch)
    ids = np.zeros((n, L), np.int64); seg = np.zeros((n, L), np.int64)
    feats = np.zeros((n, L, NFEAT), np.float32)
    mask = np.ones((n, L), bool)                           # True = PAD
    for i, b in enumerate(batch):
        k = len(b["ids"])
        ids[i, :k] = b["ids"]; seg[i, :k] = b["seg"]; feats[i, :k] = b["feats"]; mask[i, :k] = False
    return {"ids": torch.from_numpy(ids), "seg": torch.from_numpy(seg),
            "feats": torch.from_numpy(feats), "pad": torch.from_numpy(mask),
            "answerable": torch.tensor([b.get("answerable", 0) for b in batch], dtype=torch.float32),
            "start": torch.tensor([b["start"] for b in batch], dtype=torch.long),
            "end": torch.tensor([b["end"] for b in batch], dtype=torch.long),
            "has_span": torch.tensor([b["has_span"] for b in batch], dtype=torch.float32)}


def load_squad(split: str):
    from packages.reasoning_vm.ace.data import load_squad as _ls    # reuse the loader (data-only)
    return _ls(split)
