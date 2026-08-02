# -*- coding: utf-8 -*-
"""Does the self-check catch the five things that fooled us today? Authority is earned here.

    python scripts/self_check_retro.py

Giving promotion rights to a gate that cannot catch what already got through is not automation, it is
the same night repeated without anyone watching. So before `preflight.gated` is allowed to sign
anything, it is replayed against the five real failures of 2026-07-29, each reconstructed from its
recorded numbers.

Two controls, because a gate that refuses everything would score perfectly here and be worthless:

    the five failures   must ALL be refused
    two real results    must BOTH be allowed  (the depth transfer and the self-supervised ordering,
                        which were measured with controls and held up)

Passing means it separates the two. Refusing everything is a failure of this test, not a success.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.self_check.preflight import run   # noqa: E402


def _spread(centre: float, width: float, n: int = 200, seed: int = 0) -> list[float]:
    return list(np.random.default_rng(seed).normal(centre, width, n))


# Each case carries the numbers that were actually recorded on the day.
FAILURES = [
    ("occluded eye reported as CitySample",
     dict(visible_frac=0.75, base_rate=0.30, n=400,
          target_size=100.0, unit_size=10.0,
          real_score=0.999, control_score=0.999)),

    ("window order from a border artefact",
     dict(observed_source="screen", intended_source="screen", visible_frac=1.0,
          base_rate=0.50, n=27, target_size=100.0, unit_size=10.0,
          real_score=0.556, control_score=0.667)),          # trained lost to UNTRAINED

    ("object discovery in a city with no traffic",
     dict(visible_frac=1.0, base_rate=0.003, n=401,
          target_size=16.0, unit_size=1280.0,
          same=_spread(0.80, 0.10, seed=1), different=_spread(0.78, 0.10, seed=2))),

    # THE MEASURED OVERLAP, not a resampled normal. The first version of this case drew synthetic
    # same/different populations from normals with the recorded medians and spreads, and they gave a
    # 1.1% overlap where the real data gave 26-35% — because real cosine scores are bounded at 1.0
    # and heavily skewed, and a normal has no such tail. That reconstruction let the case through and
    # the check was blamed for it. The check was fine; my stand-in for the data was not.
    ("every view matched to one stored instance",
     dict(visible_frac=1.0, base_rate=0.50, n=264,
          target_size=576.0, unit_size=100.0,
          overlap=0.26)),

    ("re-identification validated pairwise instead of at scale",
     dict(visible_frac=1.0, base_rate=0.50, n=600,
          target_size=576.0, unit_size=100.0,
          real_score=0.155, control_score=0.156)),          # gallery top-1 vs threshold precision
]

REAL = [
    ("CARLA depth transfers to City Sample",
     dict(visible_frac=1.0, base_rate=1.00, n=61,
          target_size=100.0, unit_size=10.0,
          real_score=0.283, control_score=-0.006)),

    ("ordinal depth learned from motion alone",
     dict(visible_frac=1.0, base_rate=1.00, n=6426,
          target_size=100.0, unit_size=10.0,
          real_score=0.809, control_score=0.402)),
]


def main() -> None:
    rows = []
    print("=== the five that got through today — all must be REFUSED ===")
    caught = 0
    for name, kw in FAILURES:
        v = run(f"[retro] {name}", **kw)
        ok = not v.may_promote
        caught += ok
        print(f"  {'REFUSED ' if ok else 'ALLOWED!'} {name}")
        if ok:
            print(f"            {v.why_not()[0]}")
        rows.append({"case": name, "expected": "refuse", "refused": ok, **v.as_dict()})

    print("\n=== two results that held up — both must be ALLOWED ===")
    passed = 0
    for name, kw in REAL:
        v = run(f"[retro] {name}", **kw)
        ok = v.may_promote
        passed += ok
        print(f"  {'ALLOWED ' if ok else 'REFUSED!'} {name}")
        if not ok:
            print(f"            {v.why_not()}")
        rows.append({"case": name, "expected": "allow", "allowed": ok, **v.as_dict()})

    earned = caught == len(FAILURES) and passed == len(REAL)
    print(f"\ncaught {caught}/{len(FAILURES)} failures, allowed {passed}/{len(REAL)} real results")
    print(f"-> self-promotion authority {'EARNED' if earned else 'NOT EARNED'}")
    if not earned:
        print("   (a gate that refuses everything fails this test too — it must separate the two)")

    out = Path("data/self_check/retro.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"earned": earned, "caught": caught, "allowed": passed,
                               "cases": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
