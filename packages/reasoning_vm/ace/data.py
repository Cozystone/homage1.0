# -*- coding: utf-8 -*-
"""ACE data: tokenizer (60k enwiki vocab + hash buckets), word features, SQuAD-2 → tensors with
char→token span alignment. Pure numpy/regex; torch tensors are assembled in the collate step."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
EMB_DIR = REPO / "data" / "graph_scale" / "rif_enwiki_emb"
SQ = REPO / "data" / "benchmarks" / "squad2"

_WORD = re.compile(r"[A-Za-z0-9]+")
_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"}
PAD, CLS, SEP, UNK = 0, 1, 2, 3
N_SPECIAL = 4
N_HASH = 4096
NFEAT = 6
Q_MAX, P_MAX = 48, 336
SEQ_MAX = 1 + Q_MAX + 1 + P_MAX + 1        # [CLS] q [SEP] p [SEP]


class Tokenizer:
    """Word-level: special tokens, then the enwiki vocabulary, then hash buckets for OOV. The embedding
    matrix rows line up with these ids so PPMI+SVD vectors can warm-start the vocab block."""

    def __init__(self, emb):
        self.emb = emb
        self.V = len(emb.idx)
        self.vocab_base = N_SPECIAL
        self.hash_base = N_SPECIAL + self.V
        self.n_ids = N_SPECIAL + self.V + N_HASH

    def wid(self, w: str) -> int:
        i = self.emb.idx.get(w.lower())
        if i is not None:
            return self.vocab_base + i
        return self.hash_base + (hash(w.lower()) % N_HASH)

    def warmstart_matrix(self, dim: int) -> np.ndarray:
        """Embedding init: specials + hash = small random; vocab = the trained PPMI+SVD vectors."""
        rng = np.random.default_rng(0)
        M = (rng.standard_normal((self.n_ids, dim)) * 0.02).astype(np.float32)
        M[self.vocab_base:self.hash_base] = self.emb.vecs[:, :dim]
        return M


def _spans(text: str):
    return [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(text)]


def _feats(word: str, tok_lower: str, qset: set, tok, tokn: int, i: int, n: int) -> list[float]:
    rank = tok.emb.idx.get(tok_lower)
    rarity = (rank / max(1, tok.V)) if rank is not None else 1.0     # high = rare/OOV
    return [
        1.0 if word[:1].isupper() else 0.0,
        1.0 if word.isdigit() else 0.0,
        1.0 if (re.fullmatch(r"\d{3,4}", word) or tok_lower in _MONTHS) else 0.0,
        1.0 if tok_lower in qset else 0.0,
        float(rarity),
        float(i) / max(1, n),
    ]


def encode(tok: Tokenizer, question: str, context: str, ans_start: int = -1, ans_text: str = ""):
    """→ dict of arrays: ids, seg, feats, mask, plus start/end token targets (or 0=CLS for no-span)."""
    q = _spans(question)[:Q_MAX]
    p = _spans(context)
    qset = {w.lower() for w, _s, _e in q}

    ids = [CLS]
    seg = [0]
    feats = [[0.0] * NFEAT]
    # question block
    for i, (w, _s, _e) in enumerate(q):
        ids.append(tok.wid(w)); seg.append(0)
        feats.append(_feats(w, w.lower(), set(), tok, len(q), i, len(q)))
    ids.append(SEP); seg.append(0); feats.append([0.0] * NFEAT)
    p_off = len(ids)                                    # first passage token position in the sequence
    # passage block (truncated), remember each passage token's char span for answer alignment
    kept = p[:P_MAX]
    for i, (w, _s, _e) in enumerate(kept):
        ids.append(tok.wid(w)); seg.append(1)
        feats.append(_feats(w, w.lower(), qset, tok, len(kept), i, len(kept)))
    ids.append(SEP); seg.append(1); feats.append([0.0] * NFEAT)

    start_t = end_t = 0                                 # 0 = CLS = "no span" (impossible / not aligned)
    has_span = 0
    if ans_start >= 0 and ans_text:
        a0, a1 = ans_start, ans_start + len(ans_text)
        hit = [j for j, (_w, s, e) in enumerate(kept) if s < a1 and e > a0]
        if hit:
            start_t = p_off + hit[0]
            end_t = p_off + hit[-1]
            has_span = 1
    return {"ids": np.array(ids, np.int64), "seg": np.array(seg, np.int64),
            "feats": np.array(feats, np.float32), "start": start_t, "end": end_t,
            "has_span": has_span, "p_off": p_off, "p_len": len(kept),
            "p_char": [(s, e) for _w, s, e in kept]}     # char spans of kept passage tokens (for decode)


def load_squad(split: str):
    import json
    data = json.loads((SQ / f"{split}-v2.0.json").read_text(encoding="utf-8"))["data"]
    rows = []
    for art in data:
        for para in art["paragraphs"]:
            ctx = para["context"]
            for qa in para["qas"]:
                imp = bool(qa.get("is_impossible"))
                a = qa["answers"][0] if qa.get("answers") else None
                rows.append({"q": qa["question"], "ctx": ctx, "answerable": 0 if imp else 1,
                             "ans_start": (a["answer_start"] if a else -1),
                             "ans_text": (a["text"] if a else ""),
                             "golds": [x["text"] for x in qa.get("answers", [])]})
    return rows


def collate(batch, tok: Tokenizer):
    import torch
    L = max(len(b["ids"]) for b in batch)
    n = len(batch)
    ids = np.zeros((n, L), np.int64)
    seg = np.zeros((n, L), np.int64)
    feats = np.zeros((n, L, NFEAT), np.float32)
    mask = np.ones((n, L), bool)                        # True = PAD (key_padding_mask convention)
    for i, b in enumerate(batch):
        k = len(b["ids"])
        ids[i, :k] = b["ids"]; seg[i, :k] = b["seg"]; feats[i, :k] = b["feats"]; mask[i, :k] = False
    return {
        "ids": torch.from_numpy(ids), "seg": torch.from_numpy(seg),
        "feats": torch.from_numpy(feats), "pad": torch.from_numpy(mask),
        "answerable": torch.tensor([b.get("answerable", 0) for b in batch], dtype=torch.float32),
        "start": torch.tensor([b["start"] for b in batch], dtype=torch.long),
        "end": torch.tensor([b["end"] for b in batch], dtype=torch.long),
        "has_span": torch.tensor([b["has_span"] for b in batch], dtype=torch.float32),
    }
