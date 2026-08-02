# -*- coding: utf-8 -*-
"""Track F / F1 — the grounded neuro-symbolic REALIZER: symbolic bones in, fluent sentence out.

A causal decoder that reuses the ACE2 blocks (RoPE + GeGLU + pre-norm) — verified parts, re-arranged,
no new architecture. It is deliberately light (~35M, d512×8L; owner: "너무 무거워지지 않으면서도").
It learns FORM, not knowledge: conditioned on linearised bones it generates a fluent realisation, and
fact-dropout training teaches it to ABSTAIN when the bones are empty — so it never becomes a knowledge
store (the No-LLM line, measured by the G-F3 closed-book probe). The token embedding is tied to the LM
head to save parameters.

Sequence layout (causal LM, loss only on the realisation span):
    [CLS] bones: <linearised triples> [SEP] <fluent sentence> [SEP]
"""
from __future__ import annotations

import torch
import torch.nn as nn

from packages.reasoning_vm.ace.model2 import RoPE, GeGLU


class CausalBlock(nn.Module):
    def __init__(self, d_model, heads, ffn, dropout):
        super().__init__()
        self.h, self.dh = heads, d_model // heads
        self.n1 = nn.LayerNorm(d_model)
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.n2 = nn.LayerNorm(d_model)
        self.ff = GeGLU(d_model, ffn)
        self.drop = nn.Dropout(dropout)
        self.pdrop = dropout

    def _attn(self, x, rope, pad):
        B, L, D = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q = q.view(B, L, self.h, self.dh).transpose(1, 2)
        k = k.view(B, L, self.h, self.dh).transpose(1, 2)
        v = v.view(B, L, self.h, self.dh).transpose(1, 2)
        q, k = rope(q), rope(k)
        drop = self.pdrop if self.training else 0.0
        if pad is None:
            o = torch.nn.functional.scaled_dot_product_attention(q, k, v, dropout_p=drop, is_causal=True)
        else:
            # combine causal (no peeking at future = the whole point) AND pad masking into ONE additive
            # mask; SDPA forbids is_causal=True together with a custom mask, so build both by hand.
            neg = torch.finfo(q.dtype).min
            causal = torch.triu(torch.ones(L, L, dtype=torch.bool, device=q.device), diagonal=1)
            m = torch.zeros(B, 1, L, L, dtype=q.dtype, device=q.device)
            m = m.masked_fill(causal[None, None], neg)                 # future positions
            m = m.masked_fill(pad[:, None, None, :], neg)              # padded key positions
            o = torch.nn.functional.scaled_dot_product_attention(q, k, v, attn_mask=m, dropout_p=drop)
        return self.proj(o.transpose(1, 2).contiguous().view(B, L, D))

    def forward(self, x, rope, pad):
        x = x + self.drop(self._attn(self.n1(x), rope, pad))
        x = x + self.drop(self.ff(self.n2(x)))
        return x


class Realizer(nn.Module):
    def __init__(self, vocab: int, d_model: int = 512, layers: int = 8, heads: int = 8,
                 ffn: int = 1536, dropout: float = 0.1, max_len: int = 256):
        super().__init__()
        self.tok_emb = nn.Embedding(vocab, d_model, padding_idx=0)
        self.rope = RoPE(d_model // heads, max_len)
        self.blocks = nn.ModuleList([CausalBlock(d_model, heads, ffn, dropout) for _ in range(layers)])
        self.norm_f = nn.LayerNorm(d_model)
        self.lm_head = nn.Linear(d_model, vocab, bias=False)
        self.lm_head.weight = self.tok_emb.weight        # tied embedding <-> output (param saving)

    def forward(self, ids, pad=None):
        h = self.tok_emb(ids)
        for b in self.blocks:
            h = b(h, self.rope, pad)
        return self.lm_head(self.norm_f(h))              # (B, L, vocab) logits

    @torch.no_grad()
    def generate(self, prefix_ids, sep_id: int, max_new: int = 48, temperature: float = 0.7,
                 top_k: int = 40, greedy: bool = False,
                 logit_bias: "dict[int, float] | None" = None,
                 uid_penalty: float = 4.0) -> list[int]:
        """Autoregressive decode until the SEP terminator or max_new. Returns the generated ids only.
        `logit_bias` {token_id: delta} implements interactive-alignment priming (Pickering & Garrod):
        content tokens the interlocutor just used get a small positive delta, so the realizer leans
        toward the dialogue's established vocabulary — the mechanistic core of conversational feel."""
        self.eval()
        dev = self.tok_emb.weight.device
        ids = torch.tensor([prefix_ids], dtype=torch.long, device=dev)
        out: list[int] = []
        for _ in range(max_new):
            logits = self.forward(ids)[0, -1]
            if logit_bias:
                for t, d in logit_bias.items():
                    if 0 <= t < logits.shape[-1]:
                        logits[t] += d
            if uid_penalty and out:
                # UID (uniform information density): a token carrying ~zero new information is barred.
                # (1) HARD no-repeat-bigram — a candidate that would re-create an already-seen bigram is
                #     blocked outright, which structurally kills loops ("the city of the city") regardless
                #     of logit magnitude. (2) SOFT frequency penalty on over-used tokens keeps info even.
                from collections import Counter as _C
                for tok_id, c in _C(out).items():
                    logits[tok_id] -= uid_penalty * c              # soft: discourage over-use
                neg = torch.finfo(logits.dtype).min
                prev = out[-1]
                logits[prev] = neg                                 # hard: never immediately repeat a token
                for i in range(len(out) - 1):                      # hard: no seen bigram may repeat
                    if out[i] == prev:
                        logits[out[i + 1]] = neg
            if greedy:
                nxt = int(logits.argmax())
            else:
                logits = logits / max(1e-6, temperature)
                if top_k:
                    v, _ix = torch.topk(logits, min(top_k, logits.shape[-1]))
                    logits[logits < v[-1]] = torch.finfo(logits.dtype).min
                probs = torch.softmax(logits, dim=-1)
                nxt = int(torch.multinomial(probs, 1))
            if nxt == sep_id:
                break
            out.append(nxt)
            ids = torch.cat([ids, torch.tensor([[nxt]], device=dev)], dim=1)
            if ids.shape[1] >= self.rope.cos.shape[-2]:      # respect max_len
                break
        return out


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
