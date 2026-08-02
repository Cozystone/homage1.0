# -*- coding: utf-8 -*-
"""Fine-tune ATANOR's own encoder on span labels, with the one control that makes the answer mean anything.

    python scripts/ace2_finetune_spans.py [epochs]

The frozen linear probe put ACE2 BELOW 14 hand-designed feature templates (acc 0.589 against 0.620,
REL F1 0.469 against 0.564), which is a fair verdict on the representation as it stands and not on the
encoder. ACE2's objectives were RTD, inverse cloze and graph pairs; none of them is token classification,
so nothing ever asked its hidden states to make span roles linearly readable.

Fine-tuning asks a different question, and answering it needs a control the frozen probe did not:

    ACE2 pretrained + fine-tuned      does the checkpoint help
    SAME ARCHITECTURE, RANDOM INIT    would any 12-layer transformer have done as well
    hashed features (measured)        acc 0.620, REL 0.564 -- the incumbent to beat
    label-shuffled                    the floor

WITHOUT THE RANDOM-INIT ARM A WIN WOULD BE UNINTERPRETABLE. It would say "a transformer beats logistic
regression", which nobody doubts, while the question on the table is whether 325k steps of ATANOR's own
pretraining bought anything. That arm is the whole experiment; the pretrained arm is only half of it.

Both arms get the same recipe and the same two learning rates, and the better of the two is reported for
each, so neither is handicapped by a setting that happened to suit the other.

Doctrine: the checkpoint is ATANOR's own, trained from scratch. Nothing pretrained by anyone else is
loaded here or anywhere in this line.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
CKPT = REPO / "data" / "graph_scale" / "ace2_backbone.pt"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
OUT = Path("data/language/ace2_finetune_spans.json")
IGNORE = -100
HASHED = {"acc": 0.620, "f1_SUBJ": 0.536, "f1_REL": 0.564, "f1_OBJ": 0.236}


def encode(tok, words, labels, max_len: int = 128):
    """Sub-token ids with the word label on the word's FIRST sub-token and IGNORE elsewhere.

    Labelling every sub-token would let a long word outvote a short one and would score the tokenizer's
    segmentation rather than the tagger's reading."""
    text = " ".join(words)
    enc = tok.encode(text)
    starts, pos = [], 0
    for w in words:
        starts.append(text.index(w, pos))
        pos = starts[-1] + len(w)
    y = [IGNORE] * len(enc.ids)
    for wi, st in enumerate(starts):
        for ti, (a, b) in enumerate(enc.offsets):
            if a == st or (a <= st < b):
                y[ti] = labels[wi]
                break
    return enc.ids[:max_len], y[:max_len]


class SpanTagger:
    def __init__(self, pretrained: bool, vocab: int, d_model: int, dev: str):
        import torch
        import torch.nn as nn

        from packages.reasoning_vm.ace.model2 import Ace2Encoder
        self.torch = torch
        self.enc = Ace2Encoder(vocab=vocab, d_model=d_model)
        if pretrained:
            sd = torch.load(CKPT, map_location="cpu")
            self.enc.load_state_dict(sd.get("model", sd), strict=False)
        self.head = nn.Linear(d_model, 4)
        self.enc.to(dev)
        self.head.to(dev)
        self.dev = dev

    def logits(self, ids, pad):
        h = self.enc._backbone(ids, self.torch.zeros_like(ids), None, pad)
        return self.head(h)

    def fit(self, data, epochs: int, lr: float, batch: int = 24, seed: int = 0):
        torch = self.torch
        torch.manual_seed(seed)
        opt = torch.optim.AdamW(list(self.enc.parameters()) + list(self.head.parameters()), lr=lr)
        lossf = torch.nn.CrossEntropyLoss(ignore_index=IGNORE)
        rng = np.random.default_rng(seed)
        self.enc.train()
        for _ep in range(epochs):
            idx = rng.permutation(len(data))
            for k in range(0, len(idx), batch):
                chunk = [data[i] for i in idx[k:k + batch]]
                L = max(len(x) for x, _y in chunk)
                ids = torch.zeros(len(chunk), L, dtype=torch.long)
                pad = torch.ones(len(chunk), L, dtype=torch.bool)
                ys = torch.full((len(chunk), L), IGNORE, dtype=torch.long)
                for b, (x, y) in enumerate(chunk):
                    ids[b, :len(x)] = torch.tensor(x)
                    pad[b, :len(x)] = False
                    ys[b, :len(y)] = torch.tensor(y)
                out = self.logits(ids.to(self.dev), pad.to(self.dev))
                loss = lossf(out.reshape(-1, 4), ys.to(self.dev).reshape(-1))
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    list(self.enc.parameters()) + list(self.head.parameters()), 1.0)
                opt.step()
        return self

    def predict(self, data, batch: int = 32):
        torch = self.torch
        self.enc.eval()
        P, G = [], []
        with torch.no_grad():
            for k in range(0, len(data), batch):
                chunk = data[k:k + batch]
                L = max(len(x) for x, _y in chunk)
                ids = torch.zeros(len(chunk), L, dtype=torch.long)
                pad = torch.ones(len(chunk), L, dtype=torch.bool)
                for b, (x, _y) in enumerate(chunk):
                    ids[b, :len(x)] = torch.tensor(x)
                    pad[b, :len(x)] = False
                pr = self.logits(ids.to(self.dev), pad.to(self.dev)).argmax(-1).cpu().numpy()
                for b, (x, y) in enumerate(chunk):
                    for i, yy in enumerate(y[:len(x)]):
                        if yy != IGNORE:
                            P.append(int(pr[b, i]))
                            G.append(int(yy))
        return P, G


def score(pred, gold) -> dict:
    g, p = np.array(gold), np.array(pred)
    out = {"acc": float((g == p).mean())}
    for k, name in enumerate(("OUT", "SUBJ", "REL", "OBJ")):
        if k == 0:
            continue
        tp = int(((g == k) & (p == k)).sum())
        fp = int(((g != k) & (p == k)).sum())
        fn = int(((g == k) & (p != k)).sum())
        pr, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        out[f"f1_{name}"] = 2 * pr * rc / max(pr + rc, 1e-9)
    return out


def main() -> None:
    import torch
    from tokenizers import Tokenizer

    from scripts.train_frame_tagger import build_examples
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    ex, arts = build_examples()
    uniq = sorted(set(arts))
    rng = np.random.default_rng(0)
    held = set(rng.choice(uniq, size=max(2, len(uniq) // 5), replace=False).tolist())
    tr_raw = [e for e, a in zip(ex, arts) if a not in held][:6000]
    te_raw = [e for e, a in zip(ex, arts) if a in held][:1500]

    tok = Tokenizer.from_file(str(TOKJSON))
    sd = torch.load(CKPT, map_location="cpu")
    sd = sd.get("model", sd)
    vocab, d_model = sd["tok_emb.weight"].shape
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tr = [encode(tok, t, l) for t, l in tr_raw]
    te = [encode(tok, t, l) for t, l in te_raw]
    print(f"{len(tr)} train / {len(te)} test sentences, held out BY ARTICLE; "
          f"vocab {vocab}, d_model {d_model}, {dev}, {epochs} epochs\n", flush=True)

    rows = {}
    for name, pre in (("ACE2 pretrained", True), ("random init (same architecture)", False)):
        best = None
        for lr in (3e-5, 1e-4):
            m = SpanTagger(pre, vocab, d_model, dev).fit(tr, epochs, lr)
            r = score(*m.predict(te))
            r["lr"] = lr
            print(f"  {name:<34} lr {lr:.0e}  acc {r['acc']:.3f}  SUBJ {r['f1_SUBJ']:.3f}  "
                  f"REL {r['f1_REL']:.3f}  OBJ {r['f1_OBJ']:.3f}", flush=True)
            if best is None or r["acc"] > best["acc"]:
                best = r
        rows[name] = best

    shuf = [(x, [(int(v) if v == IGNORE else int(rng.integers(0, 4))) for v in y]) for x, y in tr]
    m = SpanTagger(True, vocab, d_model, dev).fit(shuf, max(1, epochs - 1), 3e-5)
    rows["label-shuffled control"] = score(*m.predict(te))
    r = rows["label-shuffled control"]
    print(f"  {'label-shuffled control':<34}          acc {r['acc']:.3f}  SUBJ {r['f1_SUBJ']:.3f}  "
          f"REL {r['f1_REL']:.3f}  OBJ {r['f1_OBJ']:.3f}", flush=True)

    a, ri = rows["ACE2 pretrained"], rows["random init (same architecture)"]
    print(f"\n  hashed features (measured earlier)          acc {HASHED['acc']:.3f}  "
          f"SUBJ {HASHED['f1_SUBJ']:.3f}  REL {HASHED['f1_REL']:.3f}  OBJ {HASHED['f1_OBJ']:.3f}")
    print(f"\n-> 1. beats the hand-designed features: {a['acc'] > HASHED['acc']}  "
          f"({HASHED['acc']:.3f} -> {a['acc']:.3f}, REL {HASHED['f1_REL']:.3f} -> {a['f1_REL']:.3f})")
    print(f"-> 2. THE PRETRAINING ITSELF EARNS ITS KEEP: {a['acc'] > ri['acc'] + 0.01}  "
          f"(pretrained {a['acc']:.3f} vs random init {ri['acc']:.3f})")
    print(f"-> 3. clears its own shuffled control: "
          f"{a['acc'] > rows['label-shuffled control']['acc'] + 0.05}")
    if a["acc"] <= ri["acc"] + 0.01:
        print("\n   Without test 2 a win says only that a transformer beats logistic regression, which")
        print("   was never in doubt. The 325k steps would then have bought nothing measurable here.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"epochs": epochs, "n_train": len(tr), "n_test": len(te),
                               "hashed_baseline": HASHED, "arms": rows}, indent=2),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
