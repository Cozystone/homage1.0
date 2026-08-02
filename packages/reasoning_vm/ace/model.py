# -*- coding: utf-8 -*-
"""ACE model — TinyEncoder: warm-started token embeddings + word features → transformer encoder →
answerability / span heads. A JUDGE, not a generator. ~12M params; runs on one consumer GPU."""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from .data import NFEAT, SEQ_MAX


class AceEncoder(nn.Module):
    def __init__(self, n_ids: int, emb_dim: int = 128, d_model: int = 256, layers: int = 5,
                 heads: int = 8, ffn: int = 512, dropout: float = 0.1, warmstart: np.ndarray | None = None):
        super().__init__()
        self.tok_emb = nn.Embedding(n_ids, emb_dim, padding_idx=0)
        if warmstart is not None:
            with torch.no_grad():
                self.tok_emb.weight.copy_(torch.from_numpy(warmstart))
        self.tok_proj = nn.Linear(emb_dim, d_model)
        self.feat_proj = nn.Linear(NFEAT, d_model)
        self.seg_emb = nn.Embedding(2, d_model)
        self.pos_emb = nn.Embedding(SEQ_MAX + 8, d_model)
        self.norm_in = nn.LayerNorm(d_model)
        layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=heads, dim_feedforward=ffn,
                                           dropout=dropout, activation="gelu", batch_first=True,
                                           norm_first=True)
        self.enc = nn.TransformerEncoder(layer, num_layers=layers)
        self.ans_head = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.Dropout(dropout),
                                      nn.Linear(d_model, 1))
        self.start_head = nn.Linear(d_model, 1)
        self.end_head = nn.Linear(d_model, 1)
        # DELIBERATOR ④: 3-way support head (SUPPORTS / NEI / REFUTES) — "does the evidence support
        # the claim?" — the judge the reasoning circuit chains over. Same body, extra head.
        self.support_head = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.Dropout(dropout),
                                          nn.Linear(d_model, 3))

    def _backbone(self, ids, seg, feats, pad):
        B, L = ids.shape
        pos = torch.arange(L, device=ids.device).unsqueeze(0).expand(B, L)
        h = self.tok_proj(self.tok_emb(ids)) + self.feat_proj(feats) + self.seg_emb(seg) + self.pos_emb(pos)
        return self.enc(self.norm_in(h), src_key_padding_mask=pad)   # (B, L, d)

    def forward(self, ids, seg, feats, pad):
        h = self._backbone(ids, seg, feats, pad)
        ans_logit = self.ans_head(h[:, 0]).squeeze(-1)            # CLS → answerability
        start = self.start_head(h).squeeze(-1)                    # (B, L)
        end = self.end_head(h).squeeze(-1)
        neg = torch.finfo(start.dtype).min
        start = start.masked_fill(pad, neg)                      # can't point at padding
        end = end.masked_fill(pad, neg)
        return ans_logit, start, end

    def support(self, ids, seg, feats, pad):
        """3-way support logits from CLS — the DELIBERATOR reader head."""
        return self.support_head(self._backbone(ids, seg, feats, pad)[:, 0])   # (B, 3)


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
