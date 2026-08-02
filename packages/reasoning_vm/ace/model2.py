# -*- coding: utf-8 -*-
"""ACE2 backbone — the deep-bet encoder (docs/ATANOR_ACE2_encoder_design.md). Byte-BPE embedding + RoPE +
GeGLU + pre-norm, 12 layers × d384 (~27.7M, same budget as ACE but 2.4× deeper and subword). Carries an
ELECTRA replaced-token-detection (RTD) discriminator head for pretraining, plus the SAME downstream head
API as AceEncoder (ans/start/end/support) so the whole fine-tune ladder + eval harness reuse unchanged.
`feats` is accepted and ignored (hand features retired). No pretrained weights. No LLM."""
from __future__ import annotations

import torch
import torch.nn as nn


class RoPE(nn.Module):
    """Rotary positional embedding — replaces the learned position table (length-extrapolating, param-free)."""
    def __init__(self, dim: int, max_len: int = 512, base: float = 10000.0):
        super().__init__()
        inv = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        t = torch.arange(max_len).float()
        freqs = torch.outer(t, inv)                       # (L, dim/2)
        emb = torch.cat([freqs, freqs], dim=-1)           # (L, dim)
        self.register_buffer("cos", emb.cos()[None, None], persistent=False)   # (1,1,L,dim)
        self.register_buffer("sin", emb.sin()[None, None], persistent=False)

    @staticmethod
    def _rotate_half(x):
        x1, x2 = x.chunk(2, dim=-1)
        return torch.cat([-x2, x1], dim=-1)

    def forward(self, x):                                 # x: (B, H, L, d_h)
        L = x.shape[-2]
        cos, sin = self.cos[..., :L, :].to(x.dtype), self.sin[..., :L, :].to(x.dtype)
        return x * cos + self._rotate_half(x) * sin


class Attention(nn.Module):
    def __init__(self, d_model, heads, dropout):
        super().__init__()
        self.h, self.dh = heads, d_model // heads
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.drop = dropout

    def forward(self, x, rope, pad):
        B, L, D = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = q.view(B, L, self.h, self.dh).transpose(1, 2)     # (B,H,L,dh)
        k = k.view(B, L, self.h, self.dh).transpose(1, 2)
        v = v.view(B, L, self.h, self.dh).transpose(1, 2)
        q, k = rope(q), rope(k)
        mask = None
        if pad is not None:
            mask = torch.zeros(B, 1, 1, L, dtype=q.dtype, device=q.device)
            mask = mask.masked_fill(pad[:, None, None, :], torch.finfo(q.dtype).min)
        o = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, attn_mask=mask, dropout_p=(self.drop if self.training else 0.0))
        o = o.transpose(1, 2).contiguous().view(B, L, D)
        return self.proj(o)


class GeGLU(nn.Module):
    def __init__(self, d_model, ffn):
        super().__init__()
        self.gate = nn.Linear(d_model, ffn)
        self.up = nn.Linear(d_model, ffn)
        self.down = nn.Linear(ffn, d_model)

    def forward(self, x):
        return self.down(torch.nn.functional.gelu(self.gate(x)) * self.up(x))


class Block(nn.Module):
    def __init__(self, d_model, heads, ffn, dropout):
        super().__init__()
        self.n1 = nn.LayerNorm(d_model)
        self.attn = Attention(d_model, heads, dropout)
        self.n2 = nn.LayerNorm(d_model)
        self.ff = GeGLU(d_model, ffn)
        self.drop = nn.Dropout(dropout)

    def forward(self, x, rope, pad):
        x = x + self.drop(self.attn(self.n1(x), rope, pad))       # pre-norm
        x = x + self.drop(self.ff(self.n2(x)))
        return x


class Ace2Encoder(nn.Module):
    def __init__(self, vocab: int, d_model: int = 384, layers: int = 12, heads: int = 6,
                 ffn: int = 1024, dropout: float = 0.1, max_len: int = 256):
        super().__init__()
        self.tok_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.seg_emb = nn.Embedding(2, d_model)
        self.rope = RoPE(d_model // heads, max_len)
        self.blocks = nn.ModuleList([Block(d_model, heads, ffn, dropout) for _ in range(layers)])
        self.norm_f = nn.LayerNorm(d_model)
        self.disc_head = nn.Linear(d_model, 1)                    # ELECTRA RTD (per-token real/replaced)
        self.ans_head = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.Dropout(dropout),
                                      nn.Linear(d_model, 1))
        self.start_head = nn.Linear(d_model, 1)
        self.end_head = nn.Linear(d_model, 1)
        self.support_head = nn.Sequential(nn.Linear(d_model, d_model), nn.GELU(), nn.Dropout(dropout),
                                          nn.Linear(d_model, 3))

    def _backbone(self, ids, seg, feats=None, pad=None):
        h = self.tok_emb(ids) + self.seg_emb(seg)                # feats retired (accepted, ignored)
        for b in self.blocks:
            h = b(h, self.rope, pad)
        return self.norm_f(h)

    def forward(self, ids, seg, feats=None, pad=None):
        h = self._backbone(ids, seg, feats, pad)
        ans = self.ans_head(h[:, 0]).squeeze(-1)
        start = self.start_head(h).squeeze(-1)
        end = self.end_head(h).squeeze(-1)
        if pad is not None:
            neg = torch.finfo(start.dtype).min
            start = start.masked_fill(pad, neg)
            end = end.masked_fill(pad, neg)
        return ans, start, end

    def discriminate(self, ids, seg, pad=None):                  # RTD pretraining head
        return self.disc_head(self._backbone(ids, seg, None, pad)).squeeze(-1)   # (B, L)

    def support(self, ids, seg, feats=None, pad=None):
        return self.support_head(self._backbone(ids, seg, feats, pad)[:, 0])


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
