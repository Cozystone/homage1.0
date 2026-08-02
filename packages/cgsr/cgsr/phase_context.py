"""Holographic phase-context for graph-native sentence generation.

Upgrades the surface-generation walk from a LOCAL Markov state (condition on the last token
only → drifts off-topic) to a SUPERPOSED context state (condition on the whole sentence so
far). Each token gets a phase vector derived from its CO-OCCURRENCE profile, so
distributionally-similar tokens share phases. The context so far is a running superposition
(a complex sum) of the emitted tokens' phasors; a candidate is scored by INTERFERENCE with
that superposition — constructive when it coheres with everything said so far, destructive
when it clashes.

No LLM, no learned weights, no backprop: phases come deterministically from corpus
co-occurrence + a fixed seeded random projection. This is the graph-native analog of what
attention gives a transformer (each step conditions on the whole context) and the reason the
benefit GROWS with corpus density — a richer co-occurrence field means sharper phases. It is a
concrete v0 of the PHFE "superpose many elements in one state, let the next choice interfere
with all of them" idea, wired into generation rather than kept as a hidden trace.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np

_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(str(text or ""))


class PhaseField:
    """Deterministic phase vector per token, derived from co-occurrence within a window."""

    def __init__(self, corpus: list[str] | tuple[str, ...], *, dim: int = 48, window: int = 2, seed: int = 1234) -> None:
        self.dim = int(dim)
        cooc: dict[str, Counter[str]] = defaultdict(Counter)
        vocab: list[str] = []
        seen: set[str] = set()
        for sentence in corpus:
            toks = _tokens(sentence)
            for t in toks:
                if t not in seen:
                    seen.add(t)
                    vocab.append(t)
            for i, left in enumerate(toks):
                for j in range(max(0, i - window), min(len(toks), i + window + 1)):
                    if j != i:
                        cooc[left][toks[j]] += 1
        self._index = {t: k for k, t in enumerate(vocab)}
        v = len(vocab)

        # carries little topical signal, so downweight it — this is what sharpens the phase
        # separation between content words as the corpus grows.
        df: Counter[str] = Counter()
        for t in vocab:
            for ctx in cooc[t]:
                df[ctx] += 1
        idf = np.ones(v, dtype=np.float64)
        for ctx, k in self._index.items():
            idf[k] = np.log((1.0 + v) / (1.0 + df.get(ctx, 0))) + 1.0
        # Fixed sign-random projection (hashing trick): deterministic, bounded dim.
        rng = np.random.default_rng(seed)
        proj = rng.standard_normal((v, self.dim)) if v else np.zeros((0, self.dim))
        # IDF-weighted co-occurrence embedding per token → project → phases in [0, 2π).
        self._phasor: dict[str, np.ndarray] = {}
        for t in vocab:
            row = np.zeros(v, dtype=np.float64)
            for ctx, c in cooc[t].items():
                row[self._index[ctx]] = c * idf[self._index[ctx]]
            n = np.linalg.norm(row)
            if n > 0:
                row /= n
            emb = row @ proj  # (dim,)
            theta = np.pi * (1.0 + np.tanh(emb))  # similar co-occurrence → similar phase
            self._phasor[t] = np.exp(1j * theta)

    def phasor(self, token: str) -> np.ndarray | None:
        return self._phasor.get(token)


class Superposition:
    """Running holographic memory of the tokens emitted so far."""

    def __init__(self, field: PhaseField, *, decay: float = 0.9) -> None:
        self.field = field
        self.decay = float(decay)
        self.acc = np.zeros(field.dim, dtype=np.complex128)

    def add(self, token: str, weight: float = 1.0) -> None:
        p = self.field.phasor(token)
        self.acc *= self.decay  # older context fades but never vanishes → long-range, bounded
        if p is not None:
            self.acc = self.acc + weight * p

    def interference(self, token: str) -> float:
        """Normalized constructive/destructive interference of a candidate with the context
        so far, in [-1, 1]. 0 when either side is empty (no opinion)."""
        p = self.field.phasor(token)
        na = float(np.linalg.norm(self.acc))
        if p is None or na == 0.0:
            return 0.0
        return float(np.real(np.vdot(self.acc, p)) / (na * float(np.linalg.norm(p)) + 1e-9))
