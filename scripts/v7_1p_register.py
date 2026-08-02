# -*- coding: utf-8 -*-
"""Register rung V7-1' — a graded filler encoder — BEFORE its first reading.

    python scripts/v7_1p_register.py

The precise read of the five substrate organs measured something stronger than axis_v7 §1's
diagnosis. §1 said the vectors are hashes of names. The measurement says the substrate has NO graded
similarity ANYWHERE, name or not:

    atom('5') vs atom('6')   -0.0062      a name hash, orthogonal as expected
    enc(5)    vs enc(6)      -0.1155      RingCodebook, built for ORDERED attributes
    enc(5)    vs enc(9)      -0.0894      and off-by-four scores HIGHER than off-by-one

`RingCodebook` draws its per-dimension phase increment as a random multiple of 2pi/M, so distinct
values are orthogonal in the aggregate. It is exactly periodic and supports the shift operator, and
it is a GROUP encoding, not a metric one. Bundled, the consequence is that resonance is the fraction
of components matching EXACTLY: a signature off by one on one probe of six scores 0.814, off by seven
scores 0.815, and both are 5/6.

So v7's claim — similar-behaving things are geometrically near — has no means of expression in the
substrate, and that is why nothing travels through it.

THE RUNG. Add a filler encoder whose resonance decays with distance, and measure that it does.

THE BAR IS THE NULL, MEASURED HERE AND WRITTEN INTO THE SEAL BEFORE THE ENCODER EXISTS. Every
threshold this project has registered by choosing a number has failed: V7-2's absolute bar sat below
chance, the first B seal's tolerance of zero was hostile to the improvement it was meant to detect,
and today the V7-1 gate was cleared at 0.98 by a null of 0.97. So the baselines below are the CURRENT
encoders' own readings, and the direction of each metric is what has to change.

WHAT WOULD KILL THE RUNG. A monotone decay no stronger than the incumbents give. That would say
graded similarity cannot be had in this substrate without replacing the algebra, and the
hyperdimensional space would be confirmed as a coding scheme for exact matches — which would be a
real finding and would redirect v7 rather than end it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.transfer_gate.manifest import Metric, freeze     # noqa: E402
from packages.vsa_reasoning.fhrr_core import RingCodebook, atom, resonance   # noqa: E402

M = 12          # value range the rung is measured over
DIM = 2048


def decay_spearman(enc) -> float:
    """Spearman between |a-b| and resonance. A graded encoder is strongly NEGATIVE; an orthogonal
    one is ~0. This is the quantity the rung turns on."""
    d, r = [], []
    for a in range(M):
        for b in range(a + 1, M):
            d.append(min(abs(a - b), M - abs(a - b)))      # ring distance
            r.append(resonance(enc(a), enc(b)))
    d, r = np.array(d, float), np.array(r, float)
    rank = lambda v: np.argsort(np.argsort(v)).astype(float)
    return float(np.corrcoef(rank(d), rank(r))[0, 1])


def near_beats_far(enc) -> float:
    """Fraction of triples where a NEARER value resonates higher than a FARTHER one. 0.5 = chance."""
    hits = tot = 0
    for a in range(M):
        for b in range(M):
            for c in range(M):
                db = min(abs(a - b), M - abs(a - b))
                dc = min(abs(a - c), M - abs(a - c))
                if db >= dc or db == 0 or dc == 0:
                    continue
                hits += resonance(enc(a), enc(b)) > resonance(enc(a), enc(c))
                tot += 1
    return hits / max(tot, 1)


def main() -> None:
    cb = RingCodebook(M, dim=DIM, tag="v7reg")
    incumbents = {
        "atom (name hash)": lambda v: atom(str(v)),
        "RingCodebook": cb.encode,
    }
    print("=== the incumbents, measured now — these become the seal's baselines ===")
    rows = {}
    for name, enc in incumbents.items():
        s, n = decay_spearman(enc), near_beats_far(enc)
        rows[name] = (s, n)
        print(f"  {name:20} decay_spearman {s:+.4f}   near_beats_far {n:.4f}")

    # The baseline is the BEST the incumbents manage, so the rung must beat the stronger of the two
    # rather than the weaker. Picking the weaker would be choosing an easy bar after seeing both.
    base_s = max(s for s, _ in rows.values())          # closest to zero / least negative = weakest decay
    base_n = max(n for _, n in rows.values())
    print(f"\nbaselines taken as the BEST incumbent: decay_spearman {base_s:+.4f}, "
          f"near_beats_far {base_n:.4f}")

    sealed = freeze(
        name="v7_1p_graded_encoder",
        surface=["packages/vsa_reasoning/fhrr_core.py"],
        eval_entry="scripts.v7_1p_measure:evaluate",
        metrics=[
            Metric("decay_spearman", round(base_s, 6), "lower_is_better",
                   "resonance must FALL with distance; a graded encoder is strongly negative"),
            Metric("near_beats_far", round(base_n, 6), "higher_is_better",
                   "fraction of triples where the nearer value resonates higher; 0.5 is chance"),
        ],
        rationale=(
            "RUNG V7-1' on the axis_v7 ladder, registered BEFORE the encoder exists and before its "
            "first reading. Measured cause: the substrate has no graded similarity anywhere — "
            "atom('5') vs atom('6') = -0.0062 and RingCodebook enc(5) vs enc(6) = -0.1155, with "
            "off-by-four scoring HIGHER than off-by-one. Bundled, resonance is the fraction of "
            "components matching exactly (0.814 off-by-one vs 0.815 off-by-seven, both 5/6). So v7's "
            "claim that similar-behaving things are geometrically near has no means of expression. "
            "BASELINES ARE THE INCUMBENT ENCODERS' OWN READINGS, not chosen numbers — every "
            "threshold this project set by choosing has failed (V7-2's bar below chance, seal 1's "
            "tolerance of zero, V7-1's gate cleared at 0.98 by a null of 0.97). The baseline is the "
            "BEST of the two incumbents so the rung cannot pass by beating the weaker. "
            "FAILING IS INFORMATIVE: it would say graded similarity cannot be had without replacing "
            "the algebra, which redirects v7 rather than ending it."))
    print(f"\nSEALED as {sealed.name}  seal={sealed.seal[:16]}...  at {sealed.frozen_at}")
    print("  the encoder does not exist yet; nothing has been read against this seal")


if __name__ == "__main__":
    main()
