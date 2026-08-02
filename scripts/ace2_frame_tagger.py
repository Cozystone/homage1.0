# -*- coding: utf-8 -*-
"""Put ATANOR's own encoder under the frame tagger, and change nothing else.

    python scripts/ace2_frame_tagger.py

The circle measured this morning has no opening from inside it: the intake needs the tagger, the tagger
needs labels, the labels come from the graph, and the graph is 98% copular because of the intake. Of the
three ways out, this is the one whose cost is already paid.

`Ace2Encoder` is ATANOR's own -- 12 layers, d_model 384, trained from scratch for 325k steps on RTD, ICT
and graph pairs. Nothing pretrained by anyone else is loaded. And `planner.py:27` records why it has
never been live: "ace2_* checkpoints only reach the live readers if Phase C beat the incumbent." This
rung is that test, run for the first time on a task the incumbent demonstrably cannot do.

THE EXPERIMENT ISOLATES THE REPRESENTATION AND NOTHING ELSE. Same labels, same held-out split by
source, same four-way linear head, same label-shuffled control. The only difference between arms is what
the head sees:

    hashed features   14 hand-designed templates over the token and its neighbours -- yesterday's tagger
    ACE2 features     the frozen backbone's hidden state for the token, pooled to word level

If the Ace2 arm wins, the ceiling was the representation and the hand-designed features were the wall.
If it does not, the gate in planner.py was right and this checkpoint has no business in the live path --
which is a real answer either way and is why the arms are run together rather than one being reported.

The backbone is FROZEN. Fine-tuning it would confound representation quality with extra fitting, and
the question here is whether the representation ATANOR already learned is better than the one I wrote.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
CKPT = REPO / "data" / "graph_scale" / "ace2_backbone.pt"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
OUT = Path("data/language/ace2_frame_tagger.json")


def load_backbone():
    import torch
    from tokenizers import Tokenizer

    from packages.reasoning_vm.ace.model2 import Ace2Encoder
    tok = Tokenizer.from_file(str(TOKJSON))
    sd = torch.load(CKPT, map_location="cpu")
    sd = sd.get("model", sd)
    vocab = sd["tok_emb.weight"].shape[0]
    d_model = sd["tok_emb.weight"].shape[1]
    model = Ace2Encoder(vocab=vocab, d_model=d_model)
    missing, unexpected = model.load_state_dict(sd, strict=False)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(dev).eval()
    for p in model.parameters():
        p.requires_grad_(False)
    print(f"Ace2 backbone: vocab {vocab}, d_model {d_model}, "
          f"{sum(p.numel() for p in model.parameters()) / 1e6:.1f}M params on {dev}")
    print(f"  load_state_dict: {len(missing)} missing, {len(unexpected)} unexpected "
          f"(heads are expected to be missing; the backbone is what matters)")
    return model, tok, dev, d_model


def word_vectors(model, tok, dev, sentences, batch: int = 32):
    """One vector per WORD: the backbone's state at the word's first sub-token.

    The labels are per word and the encoder is sub-word, so the mapping is made explicit rather than
    assumed. A word whose sub-tokens the tokenizer drops entirely gets a zero vector and is still
    scored, so a tokenizer gap shows up as poor accuracy rather than as a silently shorter sequence."""
    import torch
    out = []
    for i in range(0, len(sentences), batch):
        chunk = sentences[i:i + batch]
        encs = [tok.encode(" ".join(w)) for w in chunk]
        L = max(len(e.ids) for e in encs)
        ids = torch.zeros(len(chunk), L, dtype=torch.long)
        pad = torch.ones(len(chunk), L, dtype=torch.bool)
        for b, e in enumerate(encs):
            ids[b, :len(e.ids)] = torch.tensor(e.ids)
            pad[b, :len(e.ids)] = False
        seg = torch.zeros_like(ids)
        with torch.no_grad():
            h = model._backbone(ids.to(dev), seg.to(dev), None, pad.to(dev)).float().cpu().numpy()
        for b, (words, e) in enumerate(zip(chunk, encs)):
            text = " ".join(words)
            starts, pos = [], 0
            for w in words:
                starts.append(text.index(w, pos))
                pos = starts[-1] + len(w)
            vecs = np.zeros((len(words), h.shape[2]), np.float32)
            offs = e.offsets
            for wi, st in enumerate(starts):
                for ti, (a, b2) in enumerate(offs):
                    if a <= st < b2 or a == st:
                        vecs[wi] = h[b, ti]
                        break
            out.append(vecs)
    return out


class LinearHead:
    """The same four-way softmax head for every arm, so only the features differ."""

    def __init__(self, dim: int, n: int = 4):
        self.W = np.zeros((n, dim + 1), np.float32)

    def _p(self, x):
        z = self.W @ x
        z -= z.max()
        e = np.exp(z)
        return e / e.sum()

    def fit(self, X, Y, epochs: int = 8, lr: float = 0.05, seed: int = 0):
        rng = np.random.default_rng(seed)
        acc = np.zeros_like(self.W)
        n = 0
        idx = np.arange(len(X))
        for _ in range(epochs):
            rng.shuffle(idx)
            for k in idx:
                x = np.append(X[k], 1.0).astype(np.float32)
                p = self._p(x)
                p[Y[k]] -= 1.0
                self.W -= lr * np.outer(p, x)
                acc += self.W
                n += 1
        if n:
            self.W = acc / n            # Polyak averaging: without it the curve was non-monotone
        return self

    def predict(self, X):
        return np.array([int(np.argmax(self._p(np.append(x, 1.0).astype(np.float32)))) for x in X])


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
    from packages.cgsr.frame_tagger import features as hashed_features
    from scripts.train_frame_tagger import build_examples

    ex, arts = build_examples()
    uniq = sorted(set(arts))
    rng = np.random.default_rng(0)
    held = set(rng.choice(uniq, size=max(2, len(uniq) // 5), replace=False).tolist())
    tr = [e for e, a in zip(ex, arts) if a not in held][:6000]
    te = [e for e, a in zip(ex, arts) if a in held][:1500]
    print(f"{len(tr)} train / {len(te)} test sentences, held out BY ARTICLE\n")

    model, tok, dev, d_model = load_backbone()
    print("\nembedding with the frozen backbone...", flush=True)
    Vtr = word_vectors(model, tok, dev, [t for t, _l in tr])
    Vte = word_vectors(model, tok, dev, [t for t, _l in te])

    def flat(vs, data):
        X = np.concatenate([v for v in vs])
        Y = np.concatenate([np.array(l) for _t, l in data])
        return X, Y

    Xtr_a, Ytr = flat(Vtr, tr)
    Xte_a, Yte = flat(Vte, te)
    Xtr_h = np.stack([hashed_features(t, i) for t, _l in tr for i in range(len(t))])
    Xte_h = np.stack([hashed_features(t, i) for t, _l in te for i in range(len(t))])
    print(f"features: ACE2 {Xtr_a.shape} vs hashed {Xtr_h.shape}\n", flush=True)

    rows = {}
    for name, Xtr, Xte in (("hashed features", Xtr_h, Xte_h), ("ACE2 features", Xtr_a, Xte_a)):
        h = LinearHead(Xtr.shape[1]).fit(Xtr, Ytr)
        rows[name] = score(h.predict(Xte), Yte)
        Ysh = rng.permutation(Ytr)
        hs = LinearHead(Xtr.shape[1]).fit(Xtr, Ysh, epochs=4)
        rows[f"{name} (label-shuffled)"] = score(hs.predict(Xte), Yte)
        print(f"  {name:<32} acc {rows[name]['acc']:.3f}   "
              f"SUBJ {rows[name]['f1_SUBJ']:.3f}  REL {rows[name]['f1_REL']:.3f}  "
              f"OBJ {rows[name]['f1_OBJ']:.3f}", flush=True)
        print(f"  {name + ' (shuffled)':<32} acc {rows[f'{name} (label-shuffled)']['acc']:.3f}   "
              f"SUBJ {rows[f'{name} (label-shuffled)']['f1_SUBJ']:.3f}  "
              f"REL {rows[f'{name} (label-shuffled)']['f1_REL']:.3f}  "
              f"OBJ {rows[f'{name} (label-shuffled)']['f1_OBJ']:.3f}", flush=True)

    a, h = rows["ACE2 features"], rows["hashed features"]
    print(f"\n-> ACE2 beats the hand-designed features: {a['acc'] > h['acc']}  "
          f"(acc {h['acc']:.3f} -> {a['acc']:.3f}, REL {h['f1_REL']:.3f} -> {a['f1_REL']:.3f})")
    print(f"-> and clears its own shuffled control: "
          f"{a['acc'] > rows['ACE2 features (label-shuffled)']['acc'] + 0.05}")
    print("\nPhase C, which planner.py:27 requires before this checkpoint may reach a live reader,")
    print(f"   is {'MET on this task' if a['acc'] > h['acc'] and a['f1_REL'] > h['f1_REL'] else 'NOT met'}"
          f" -- and this is the first time it has been put to the test on one the incumbent cannot do.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n_train": len(tr), "n_test": len(te), "d_model": d_model,
                               "arms": rows}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
