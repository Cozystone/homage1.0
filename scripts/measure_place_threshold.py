# -*- coding: utf-8 -*-
"""How different do two views have to be before they are different PLACES? Measured, not guessed.

    python scripts/measure_place_threshold.py

`explore.NEW_PLACE` decides whether curiosity found somewhere new, and the first version of it was a
number I picked with a comment asserting a scale I had not checked. It claimed consecutive City
Sample frames read 0.01-0.03; they read 0.0002. Being wrong by fifty times set the floor above every
reading the live run produced, so ATANOR explored for seventy steps, saw a different part of the
city several times over, and recorded that it had found nothing.

The right way to set a decision threshold is to measure the two things it separates and check that
they are separable at all. That is what this does, on frames already captured:

    same place   consecutive frames of one spot
    elsewhere    frames from far apart in the same drive

If those two bands overlap, no threshold works and the retinal code is the wrong instrument — which
would be worth knowing and is the outcome this script is willing to report. They do not overlap, so
any value in the gap does the job and the exact one is not delicate.

The nearest-in-memory column is the quantity `explore` actually uses. It runs the real rule over the
recorded drive — remember a view only when it clears the floor — and reports how many distinct places
that drive would have been credited with.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.attention import change_energy, frame_signature   # noqa: E402

DRIVES = Path(r"D:\citysample_drive")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=700, help="frames read per run")
    ap.add_argument("--floors", default="0.005,0.01,0.02,0.04,0.06")
    args = ap.parse_args()

    runs = [d for d in sorted(DRIVES.glob("*")) if d.is_dir() and list(d.glob("*.npz"))]
    if not runs:
        sys.exit(f"no captured frames under {DRIVES}")

    report: dict[str, dict] = {}
    for run in runs:
        files = sorted(run.glob("*.npz"))[:args.limit]
        if len(files) < 50:
            continue
        codes = [frame_signature(np.load(p)["rgb"]) for p in files]
        r: dict = {"frames": len(codes), "gaps": {}}
        for gap in (1, 60, 200, 600):
            if len(codes) <= gap:
                continue
            a = np.array([change_energy(codes[i], codes[i + gap]) for i in range(len(codes) - gap)])
            r["gaps"][f"+{gap}"] = {"median": round(float(np.median(a)), 5),
                                    "p10": round(float(np.percentile(a, 10)), 5),
                                    "p90": round(float(np.percentile(a, 90)), 5)}
        # the live rule, replayed at each candidate floor
        r["places_at_floor"] = {}
        for floor in (float(x) for x in args.floors.split(",")):
            seen = [codes[0]]
            for c in codes[1:]:
                if min(change_energy(c, s) for s in seen) >= floor:
                    seen.append(c)
            r["places_at_floor"][f"{floor}"] = len(seen)
        report[run.name] = r

        print(f"\n{run.name}  ({len(codes)} frames)")
        for k, v in r["gaps"].items():
            print(f"  gap {k:6s} median {v['median']:.5f}   p10 {v['p10']:.5f}   p90 {v['p90']:.5f}")
        print("  places found at floor: " +
              "  ".join(f"{k}->{v}" for k, v in r["places_at_floor"].items()))

    # Are the two bands separable? Same-place p90 against elsewhere p10, across runs.
    same = [r["gaps"]["+1"]["p90"] for r in report.values() if "+1" in r["gaps"]]
    far = [r["gaps"]["+600"]["p10"] for r in report.values() if "+600" in r["gaps"]]
    if same and far:
        print(f"\nsame-place p90 (worst) {max(same):.5f}   elsewhere p10 (worst) {min(far):.5f}")
        print("SEPARABLE — any floor in that gap works" if max(same) < min(far)
              else "NOT SEPARABLE — the retinal code cannot tell these apart; no floor will help")

    out = DRIVES / "place_threshold.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
