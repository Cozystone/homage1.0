# -*- coding: utf-8 -*-
"""Algebraic rule inference — the NVSA idea wired into ATANOR's reasoning lane.

Instead of SEARCHING a program space for a transformation, INFER it by one unbind:

    T_j = unbind( encode(output_j), encode(input_j) )      # per train pair j

If the T_j AGREE (consensus) the transformation is a genuine algebraic group action on the attribute
ring — a single T that maps input→output for EVERY value, including ones never seen in training. If
they disagree, there is no such algebraic rule and the lane ABSTAINS (returns None). A rule that
passes consensus is then re-VERIFIED: it must reproduce every train pair EXACTLY when applied, or it
is discarded. Propose (fast unbind) — verify (exact replay). 0 fabrication.

This is deliberately narrow: it cracks ADDITIVE SHIFTS on a cyclic attribute (a cyclic colour
rotation) and TRANSLATIONS in space. It does NOT crack an arbitrary lookup table — and it should not
pretend to: an arbitrary permutation yields an inconsistent T and is correctly refused. That refusal
is the honest boundary between "algebraic rule" and "table".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np

from packages.vsa_reasoning.fhrr_core import (
    RingCodebook,
    bind,
    unbind,
    resonance,
    cleanup,
)

Grid = list[list[int]]

CONSENSUS_TAU = 0.98   # exact additive shifts give pairwise resonance 1.0; 0.98 rejects any non-shift


# ============================================================ generic 1-D shift rule
@dataclass
class ShiftRule:
    """An additive shift c → (c + k) mod M on a cyclic attribute, inferred by unbinding.

    ``k`` is the decoded integer shift; ``codebook`` is the ring it lives on. ``consensus`` is the
    minimum pairwise resonance of the per-pair T vectors (1.0 = the pairs agreed exactly)."""
    codebook: RingCodebook
    k: int
    consensus: float

    def apply(self, value: int) -> int:
        """Apply algebraically: decode( T ⊛ φ(value) ). Generalizes to values unseen in training."""
        q = bind(self.codebook.shift_vector(self.k), self.codebook.encode(value))
        val, _ = self.codebook.decode(q)
        return int(val)


def infer_shift_rule(
    train_pairs: Sequence[tuple[int, int]],
    codebook: RingCodebook,
    *,
    tau: float = CONSENSUS_TAU,
) -> ShiftRule | None:
    """Infer an additive-shift rule from (input_value, output_value) pairs, or None (abstain).

    Steps: (1) T_j = unbind(φ(out_j), φ(in_j)) per pair; (2) consensus — every T_j must resonate
    with the bundle mean ≥ tau; (3) decode the integer shift k by cleaning the mean T against the
    shift codebook; (4) VERIFY the decoded rule reproduces every pair exactly. Any failure → None."""
    pairs = [(int(a), int(b)) for a, b in train_pairs]
    if not pairs:
        return None
    ts = [unbind(codebook.encode(b), codebook.encode(a)) for a, b in pairs]
    mean_t = np.mean(np.stack(ts), axis=0)
    consensus = min(resonance(t, mean_t) for t in ts)
    if consensus < tau:
        return None  # the per-pair transformations disagree -> not an algebraic shift -> abstain
    # decode k: nearest shift atom to the consensus T
    shift_cb = np.stack([codebook.shift_vector(k) for k in range(codebook.M)])
    shift_labels = list(range(codebook.M))
    k, kres = cleanup(mean_t, shift_cb, shift_labels)
    if k is None or kres < tau:
        return None
    rule = ShiftRule(codebook=codebook, k=int(k), consensus=float(consensus))
    # verify: exact replay of every train pair (propose-verify honesty gate)
    for a, b in pairs:
        if rule.apply(a) != b:
            return None
    return rule


# ============================================================ colour-map rule on grids (ARC lane)
@dataclass
class ColorMapRule:
    """A grid→grid recolour that is a cyclic colour ROTATION (additive shift on the colour ring),
    inferred algebraically. ``apply_grid`` recolours every cell — including colours absent from
    training — which a learned lookup TABLE cannot do (it abstains on an unseen colour)."""
    shift: ShiftRule
    covered_inputs: frozenset          # colours actually witnessed in the train maps
    def apply_grid(self, g: Grid) -> Grid:
        return [[self.shift.apply(v) for v in row] for row in g]


def _same_dims(pairs: Sequence[tuple[Grid, Grid]]) -> bool:
    return all(len(gi) == len(go) and all(len(a) == len(b) for a, b in zip(gi, go))
               for gi, go in pairs)


def infer_colormap_rule(
    train: Sequence[tuple[Grid, Grid]],
    *,
    modulus: int = 10,
    dim: int = 2048,
    seed: int = 7,
    tau: float = CONSENSUS_TAU,
) -> ColorMapRule | None:
    """Infer a cyclic-rotation recolour from same-shape grid pairs, or None (abstain).

    Collect the per-cell (in_colour → out_colour) observations; if any in_colour maps to two
    different out_colours it is not even a function → None. Otherwise feed the unique observations to
    ``infer_shift_rule`` on a colour ring. A rule is returned only if it is a consistent additive
    shift AND reproduces every train pair exactly. (ARC's colour 0 is usually background; a genuine
    rotation must therefore also satisfy 0→0, i.e. k=0 — so this fits ARC only when the true rule
    really is a ring rotation, which is the honest, measured boundary.)"""
    if not train or not _same_dims(train):
        return None
    obs: dict[int, int] = {}
    for gi, go in train:
        for ri, ro in zip(gi, go):
            for a, b in zip(ri, ro):
                a, b = int(a), int(b)
                if a in obs and obs[a] != b:
                    return None  # not a function -> no rule
                obs[a] = b
    if not obs:
        return None
    cb = RingCodebook(modulus, dim=dim, seed=seed, tag="color")
    shift = infer_shift_rule(list(obs.items()), cb, tau=tau)
    if shift is None:
        return None
    rule = ColorMapRule(shift=shift, covered_inputs=frozenset(obs))
    # final full-grid verify (belt-and-suspenders over the atomic verify inside infer_shift_rule)
    for gi, go in train:
        if rule.apply_grid(gi) != go:
            return None
    return rule


# ============================================================ 2-D translation rule (position shift)
@dataclass
class PositionShiftRule:
    """A translation (r,c) → (r+dr, c+dc) on a torus, inferred by unbinding position bindings."""
    row_cb: RingCodebook
    col_cb: RingCodebook
    dr: int
    dc: int
    consensus: float

    def apply(self, pos: tuple[int, int]) -> tuple[int, int]:
        r, c = pos
        return (int(r + self.dr) % self.row_cb.M, int(c + self.dc) % self.col_cb.M)


def _encode_pos(row_cb: RingCodebook, col_cb: RingCodebook, pos: tuple[int, int]) -> np.ndarray:
    r, c = pos
    return bind(row_cb.encode(r), col_cb.encode(c))


def infer_position_shift_rule(
    train_pairs: Sequence[tuple[tuple[int, int], tuple[int, int]]],
    *,
    n_rows: int,
    n_cols: int,
    dim: int = 2048,
    seed: int = 7,
    tau: float = CONSENSUS_TAU,
) -> PositionShiftRule | None:
    """Infer a single translation (dr,dc) from (in_pos, out_pos) pairs, or None (abstain).

    φ(r,c) = row_ring(r) ⊛ col_ring(c); T = unbind(φ(out), φ(in)) = row_shift(dr) ⊛ col_shift(dc).
    Consensus across all pairs, then decode (dr,dc) against the joint shift codebook and verify."""
    pairs = list(train_pairs)
    if not pairs:
        return None
    row_cb = RingCodebook(n_rows, dim=dim, seed=seed, tag="row")
    col_cb = RingCodebook(n_cols, dim=dim, seed=seed + 1, tag="col")
    ts = [unbind(_encode_pos(row_cb, col_cb, o), _encode_pos(row_cb, col_cb, i)) for i, o in pairs]
    mean_t = np.mean(np.stack(ts), axis=0)
    consensus = min(resonance(t, mean_t) for t in ts)
    if consensus < tau:
        return None
    # joint decode of (dr, dc) against the torus shift codebook
    shift_cb, shift_labels = [], []
    for dr in range(n_rows):
        for dc in range(n_cols):
            shift_cb.append(bind(row_cb.shift_vector(dr), col_cb.shift_vector(dc)))
            shift_labels.append((dr, dc))
    lab, lres = cleanup(mean_t, np.stack(shift_cb), shift_labels)
    if lab is None or lres < tau:
        return None
    dr, dc = lab
    rule = PositionShiftRule(row_cb, col_cb, int(dr), int(dc), float(consensus))
    for i, o in pairs:  # verify exact replay
        if rule.apply(i) != (int(o[0]) % n_rows, int(o[1]) % n_cols):
            return None
    return rule
