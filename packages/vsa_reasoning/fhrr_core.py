# -*- coding: utf-8 -*-
"""FHRR core for VSA reasoning — REUSE of the holographic substrate + a ring encoder.

REUSED (read-only import from ``packages/cgsr/cgsr/holographic_lm.py``):
  * ``HoloSpace``  (holographic_lm.py:45)  — per-symbol unit-phasor atom, deterministic hash seed.
  * ``HoloSpace.bind``   (line 63)         — element-wise phasor product = phase addition (FHRR bind).
  * ``HoloSpace.unbind`` (line 67)         — multiply by conjugate = phase subtraction (invert bind).
  * ``resonance``        (line 71)         — normalized Re<q,r> in [-1,1] (the fold-core physics).
We re-export those primitives unchanged so this package adds NO second implementation of the algebra.

NEW here (``holographic_lm`` has no ring): the FRACTIONAL-POWER / RING encoder ``RingCodebook``.
For a cyclic attribute of modulus M we set φ(c) = B^c where B is a fixed unit phasor whose phases are
multiples of 2π/M. Then:

    φ(c + k mod M) = B^(c+k) = B^k ⊛ B^c = T_k ⊛ φ(c)     for EVERY c,

so a single unbind recovers the SAME transformation T_k from any (c, c+k) pair, and applying T_k to a
value never seen in training still decodes to the right atom. That is the one property a lookup TABLE
cannot have and the whole reason VSA algebra generalizes an additive rule from a couple of examples.
An arbitrary (non-additive) map yields a DIFFERENT T per pair → consensus fails → the lane abstains.
This is the honest boundary: VSA cracks GROUP ACTIONS, not arbitrary tables.
"""
from __future__ import annotations

import numpy as np

# --- REUSED algebra (no reimplementation) -----------------------------------------------------
from packages.cgsr.cgsr.holographic_lm import HoloSpace, resonance as _resonance

resonance = _resonance  # re-export the fold-core physics unchanged


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """FHRR bind = element-wise phasor product (phase addition). Reuses HoloSpace.bind semantics."""
    return HoloSpace.bind(a, b)


def unbind(c: np.ndarray, a: np.ndarray) -> np.ndarray:
    """FHRR unbind = multiply by conjugate (phase subtraction). Reuses HoloSpace.unbind semantics."""
    return HoloSpace.unbind(c, a)


def superpose(*vs: np.ndarray) -> np.ndarray:
    """Bundle = sum of phasor vectors (the FHRR superposition). Empty → zero-length guard upstream."""
    if not vs:
        raise ValueError("superpose needs at least one vector")
    acc = np.array(vs[0], dtype=np.complex128)
    for v in vs[1:]:
        acc = acc + v
    return acc


_SHARED_SPACE = HoloSpace(dim=2048, seed=7)


def atom(symbol: str, *, space: HoloSpace | None = None) -> np.ndarray:
    """A per-symbol phasor atom (REUSED HoloSpace.vec). Used for roles / discrete tokens that have
    no ring order (unlike RingCodebook, which is for ordered/cyclic attributes)."""
    return (space or _SHARED_SPACE).vec(symbol)


def cleanup(q: np.ndarray, codebook: "np.ndarray", labels: list) -> tuple[object, float]:
    """Nearest-atom decode: return (label, resonance) of the codebook atom most resonant with q.

    ``codebook`` is an (N, D) complex matrix (rows = atoms), ``labels`` the N atom labels. This is the
    associative 'clean-up memory' of a VSA: an approximate/noisy vector snaps to the nearest stored
    symbol."""
    if codebook.shape[0] == 0:
        return None, 0.0
    nq = float(np.linalg.norm(q))
    if nq == 0.0:
        return None, 0.0
    # rows are unit-norm phasors (‖·‖ = sqrt(D)); normalize both sides -> cosine of phase interference
    row_norms = np.linalg.norm(codebook, axis=1)
    sims = (codebook @ np.conj(q)).real / (row_norms * nq + 1e-12)
    k = int(np.argmax(sims))
    return labels[k], float(sims[k])


class RingCodebook:
    """Fractional-power (ring) encoder for an ordered/cyclic attribute of modulus M.

    φ(c) = B^c, phases of B drawn as 2π·k_d/M so the encoding is exactly periodic mod M. Provides the
    codebook matrix + labels for clean-up decode. Deterministic (seeded), no training, No-LLM.
    """

    def __init__(self, modulus: int, *, dim: int = 2048, seed: int = 7, tag: str = "ring") -> None:
        if modulus < 2:
            raise ValueError("RingCodebook modulus must be >= 2")
        self.M = int(modulus)
        self.dim = int(dim)
        self.seed = int(seed)
        self.tag = str(tag)
        # Base phasor B: phases 2π·k_d/M, k_d in [1, M-1] (avoid the degenerate all-zero phase).
        rng = np.random.default_rng((hash((tag, self.M, seed)) & ((1 << 63) - 1)) or 1)
        k = rng.integers(1, self.M, size=self.dim)
        self._base_phase = (2.0 * np.pi / self.M) * k  # θ_B
        # Precompute the codebook atoms φ(0..M-1) for clean-up.
        cols = [self.encode(v) for v in range(self.M)]
        self._codebook = np.stack(cols)              # (M, D)
        self._labels = list(range(self.M))

    def encode(self, value: int) -> np.ndarray:
        """φ(value) = B^value = exp(i · value · θ_B). Periodic mod M."""
        v = int(value) % self.M
        return np.exp(1j * v * self._base_phase)

    def shift_vector(self, k: int) -> np.ndarray:
        """T_k = B^k — the transformation that maps φ(c) → φ(c+k) for every c."""
        return np.exp(1j * (int(k) % self.M) * self._base_phase)

    @property
    def codebook(self) -> np.ndarray:
        return self._codebook

    @property
    def labels(self) -> list:
        return list(self._labels)

    def decode(self, q: np.ndarray) -> tuple[int, float]:
        """Clean-up: nearest ring atom to q, returns (value, resonance)."""
        return cleanup(q, self._codebook, self._labels)  # type: ignore[return-value]

class GradedCodebook:
    """Fractional power encoding whose resonance FALLS with distance — the one thing this substrate
    could not express.

    WHY `RingCodebook` DOES NOT DO THIS, measured rather than assumed. It draws each dimension's
    phase increment as `2pi*k_d/M` with `k_d` uniform on [1, M-1]. Summed over two thousand
    dimensions those increments cancel for every pair of distinct values, so the encoding is exactly
    periodic and every distinct value is orthogonal to every other:

        enc(5) vs enc(6)  -0.1155        enc(5) vs enc(9)  -0.0894
        decay_spearman +0.0585           near_beats_far 0.5200   (chance)

    Off-by-four scores HIGHER than off-by-one. That is a GROUP encoding: it supports the shift
    operator `T_k` exactly, and it carries no metric at all.

    The difference here is one line. The phase increment is drawn from a NARROW band rather than
    uniformly over the ring, so `<phi(a), phi(b)>` is a sum of `exp(i(a-b)*theta_d)` with the
    `theta_d` clustered, and that sum decays with |a-b| instead of cancelling. The kernel is the
    characteristic function of the phase distribution, which is the standard fractional-power-encoding
    result; `bandwidth` is its width and sets how fast similarity falls off.

    Periodicity is given up. `phi(c+M) != phi(c)` here, and that is the trade: a metric encoding and
    an exactly cyclic one are different objects, so this does not replace `RingCodebook` for the
    cyclic attributes it was built for. It is an addition, and the organs that need exact matching
    should keep using atoms."""

    def __init__(self, span: int, *, dim: int = 2048, seed: int = 7, bandwidth: float = 0.35,
                 tag: str = "graded") -> None:
        if span < 2:
            raise ValueError("GradedCodebook span must be >= 2")
        self.span = int(span)
        self.dim = int(dim)
        self.bandwidth = float(bandwidth)
        rng = np.random.default_rng((hash((tag, self.span, seed)) & ((1 << 63) - 1)) or 1)
        # narrow band -> characteristic function decays smoothly with |a-b|
        self._theta = rng.normal(0.0, self.bandwidth, self.dim)

    def encode(self, value: float) -> np.ndarray:
        return np.exp(1j * float(value) * self._theta)

    def shift_vector(self, k: float) -> np.ndarray:
        """T_k maps phi(c) -> phi(c+k) for every c, exactly as in the ring case."""
        return np.exp(1j * float(k) * self._theta)

    @property
    def codebook(self) -> np.ndarray:
        return np.stack([self.encode(v) for v in range(self.span)])

    @property
    def labels(self) -> list:
        return list(range(self.span))

    def decode(self, q: np.ndarray) -> tuple[int, float]:
        cb = self.codebook
        sims = [resonance(q, cb[i]) for i in range(len(cb))]
        i = int(np.argmax(sims))
        return i, float(sims[i])
