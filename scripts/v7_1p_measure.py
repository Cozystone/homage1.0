# -*- coding: utf-8 -*-
"""The eval entry the V7-1' seal names. Reads the graded encoder against the frozen baselines.

    python scripts/v7_1p_measure.py

AT THE CLASS DEFAULT, NOT AT THE BEST OF A SWEEP. Four bandwidths were tried while building the
encoder and they all clear the seal, the strongest by a wide margin. Reporting that one would be
choosing a parameter against the sealed metric after seeing it — the same move as re-cutting a seal,
wearing different clothes. So this reads `GradedCodebook`'s own default and the sweep is reported
beside it as a sweep.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.vsa_reasoning.fhrr_core import GradedCodebook, resonance   # noqa: E402

SPAN = 12
DIM = 2048


def _decay_spearman(enc) -> float:
    d, r = [], []
    for a in range(SPAN):
        for b in range(a + 1, SPAN):
            d.append(min(abs(a - b), SPAN - abs(a - b)))
            r.append(resonance(enc(a), enc(b)))
    d, r = np.array(d, float), np.array(r, float)
    rank = lambda v: np.argsort(np.argsort(v)).astype(float)
    return float(np.corrcoef(rank(d), rank(r))[0, 1])


def _near_beats_far(enc) -> float:
    hits = tot = 0
    for a in range(SPAN):
        for b in range(SPAN):
            for c in range(SPAN):
                db = min(abs(a - b), SPAN - abs(a - b))
                dc = min(abs(a - c), SPAN - abs(a - c))
                if db >= dc or db == 0 or dc == 0:
                    continue
                hits += resonance(enc(a), enc(b)) > resonance(enc(a), enc(c))
                tot += 1
    return hits / max(tot, 1)


def evaluate() -> dict[str, float]:
    """What the seal reads. Class default bandwidth, no tuning against the metric."""
    g = GradedCodebook(SPAN, dim=DIM, tag="v7reg")        # default bandwidth
    return {"decay_spearman": round(_decay_spearman(g.encode), 6),
            "near_beats_far": round(_near_beats_far(g.encode), 6)}


def main() -> None:
    from packages.transfer_gate.manifest import load
    from packages.transfer_gate.verdict import measure

    sealed = load("v7_1p_graded_encoder")
    now = evaluate()
    print(f"seal {sealed.seal[:16]}...  frozen {sealed.frozen_at}")
    print(f"reading at the class default bandwidth={GradedCodebook(SPAN).bandwidth}\n")
    for m in sealed.metrics:
        print(f"  {m.name:16} baseline {m.baseline:+.4f} -> now {now[m.name]:+.4f}   ({m.direction})")

    try:
        v = read(sealed, now)
        print(f"\nVERDICT: {v}")
    except Exception:
        ok = all(m.improved(now[m.name]) for m in sealed.metrics)
        print(f"\nVERDICT: {'IMPROVED' if ok else 'REGRESSED'} "
              f"({sum(m.improved(now[m.name]) for m in sealed.metrics)}/{len(sealed.metrics)} metrics)")

    print("\nsweep, reported as a sweep and NOT as the result:")
    for bw in (0.15, 0.35, 0.80, 1.50):
        g = GradedCodebook(SPAN, dim=DIM, bandwidth=bw, tag="v7reg")
        print(f"  bandwidth {bw:.2f}   decay {_decay_spearman(g.encode):+.4f}   "
              f"near_beats_far {_near_beats_far(g.encode):.4f}")


if __name__ == "__main__":
    main()
