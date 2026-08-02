# -*- coding: utf-8 -*-
"""A learned frame tagger: which tokens are the subject, the relation, and the object.

The missing organ, named in ATANOR_understanding_by_regeneration_2026-07-29.md and confirmed by
measurement: 387 of 600 SQuAD questions died BEFORE any matching, in question transformation, and the
regex path cannot represent an imperative at all because `builder.py:151` excludes position 0 from the
verb search while an imperative's verb IS at position 0.

Understanding-by-regeneration solved ambiguity but inherits a hard ceiling -- it can only read what the
speaker can say, which is 32.8% of human prose. A tagger does not: it reads the sentence and proposes
spans whether or not any known construction produces it. That is the whole point of building it.

WHERE THE LINE IS, because the standing rules are easy to launder here.

    no pretrained anything     no spaCy, no NLTK, no LLM, no external tagger. Weights start at zero and
                               are fitted here.
    labels are not regex       a rule-generated label set would be a training wheel wearing a lab coat:
                               the model would learn the rule, and the rule's failures with it. The
                               labels come from ALIGNMENT -- bones whose subject and object were located
                               in a HUMAN sentence -- which is supervision the corpus already contains.
    evaluation is human text   training on self-generated sentences teaches the speaker's own habits and
                               calls it English. Held out by ARTICLE, not by sentence, so a paraphrase
                               of a training sentence cannot leak in.
    abstention survives        the tagger PROPOSES. Verification by regeneration still decides, and a
                               proposal that cannot be checked is reported as unverified rather than
                               asserted.

The model is a multinomial logistic regression over hashed context features, fitted by SGD. Small on
purpose: the claim to be tested is that a LEARNED tagger reads what a hand-written one cannot, and the
smallest learner that can show it is the one that shows it least ambiguously.
"""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

import numpy as np

LABELS = ("OUT", "SUBJ", "REL", "OBJ")
DIM = 4096
_W = re.compile(r"[^a-z0-9 ]+")


def norm(s: str) -> str:
    return " ".join(_W.sub(" ", (s or "").lower()).split())


def _h(*parts) -> int:
    """A STABLE hash. Python's built-in `hash()` is salted per process, so using it here meant the
    feature space was different on every run: the same corpus scored F1_REL 0.574 in one process and
    0.194 in another, and `save`/`load` were meaningless because restored weights indexed buckets that
    no longer meant anything. Every number this tagger produced before this line was fixed is
    withdrawn, including the imperative failure, which was measured through loaded weights."""
    return zlib.crc32("␟".join(str(p) for p in parts).encode("utf-8")) % DIM


def features(tokens: list, i: int) -> np.ndarray:
    """Context around one token. Every feature is read off the sentence; none is a rule about English."""
    x = np.zeros(DIM, np.float32)
    n = max(len(tokens), 1)
    w = tokens[i]
    lw = w.lower()
    prev = tokens[i - 1].lower() if i > 0 else "<s>"
    nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else "</s>"
    for f in (_h("w", lw), _h("p", prev), _h("n", nxt), _h("pw", prev, lw), _h("wn", lw, nxt),
              _h("cap", w[:1].isupper()), _h("dig", any(c.isdigit() for c in w)),
              _h("first", i == 0), _h("last", i == n - 1),
              _h("rel", int(10 * i / n)), _h("len", min(len(w), 12)),
              _h("suf", lw[-3:]), _h("pre", lw[:3]),
              _h("capprev", prev[:1].isupper() if prev else False)):
        x[f] += 1.0
    x[0] = 1.0
    return x


class FrameTagger:
    """Token -> OUT / SUBJ / REL / OBJ. Weights start at zero; nothing is inherited."""

    def __init__(self, dim: int = DIM):
        self.W = np.zeros((len(LABELS), dim), np.float32)

    def _scores(self, x: np.ndarray) -> np.ndarray:
        z = self.W @ x
        z -= z.max()
        e = np.exp(z)
        return e / e.sum()

    def fit(self, data, epochs: int = 6, lr: float = 0.12, seed: int = 0,
            average: bool = True) -> dict:
        """SGD with POLYAK AVERAGING, which is the difference between a result and a coin flip here.

        Without averaging the same corpus gave F1_REL 0.525 at 1,068 sentences, 0.095 at 2,137, 0.560
        at 4,274 and 0.185 at all 8,549 -- non-monotone in data size and swinging by a factor of six,
        because the final weights of a constant-rate SGD on an imbalanced four-class problem are set by
        whatever the last few updates were. Averaging the iterates removes that dependence; it is the
        textbook remedy and not a tuning trick."""
        rng = np.random.default_rng(seed)
        order = np.arange(len(data))
        hist = []
        acc = np.zeros_like(self.W)
        n_upd = 0
        for _ep in range(epochs):
            rng.shuffle(order)
            loss = 0.0
            for idx in order:
                toks, labs = data[idx]
                for i, y in enumerate(labs):
                    x = features(toks, i)
                    p = self._scores(x)
                    loss -= float(np.log(max(p[y], 1e-9)))
                    p[y] -= 1.0
                    self.W -= lr * np.outer(p, x)
                    acc += self.W
                    n_upd += 1
            hist.append(loss / max(sum(len(l) for _t, l in data), 1))
        if average and n_upd:
            self.W = acc / n_upd
        return {"epochs": epochs, "loss": hist, "averaged": bool(average and n_upd)}

    def tag(self, tokens: list) -> list:
        return [int(np.argmax(self._scores(features(tokens, i)))) for i in range(len(tokens))]

    def spans(self, sentence: str, require_subject: bool = True):
        """(subject, relation, object) read off the tag sequence.

        The sentence is normalised EXACTLY as the training text was. Feeding raw text at inference
        while training on normalised text silently changed the suffix and capitalisation features --
        'office.' has the suffix 'ce.' where training saw 'ice' -- and every token came back OUT. The
        imperative test was measuring that mismatch, not the tagger.

        require_subject=False is for imperatives, whose subject is the addressee and is not in the
        sentence at all. Demanding a SUBJ span from a command is demanding it not be a command."""
        toks = norm(sentence).split()
        if not toks:
            return None
        tags = self.tag(toks)
        out = {}
        for k, name in enumerate(LABELS):
            if k == 0:
                continue
            got = [t for t, g in zip(toks, tags) if g == k]
            out[name] = " ".join(got) if got else None
        if not out.get("REL") or (require_subject and not out.get("SUBJ")):
            return None
        return out.get("SUBJ") or "", out["REL"], out.get("OBJ") or ""

    def save(self, path: Path) -> None:
        np.savez_compressed(path, W=self.W)

    @classmethod
    def load(cls, path: Path) -> "FrameTagger":
        t = cls()
        t.W = np.load(path)["W"]
        return t
