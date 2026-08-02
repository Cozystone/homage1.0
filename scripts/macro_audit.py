# -*- coding: utf-8 -*-
"""Where the hand-chosen numbers are, and which organs nothing imports. A whole-repo view, re-runnable.

    python scripts/macro_audit.py

WHY THIS EXISTS. Perception work had run for many rungs in a row -- foveation, page skeletons, a text
layer, a grouping organ -- each one a real measurement, and none of them asking whether that axis was the
one worth the depth. The owner asked for the macro view. This is it, as numbers rather than as an opinion.

TWO THINGS ARE MEASURED, because they are the two shapes the same pathology takes.

  ORGANS NOTHING IMPORTS. An organ built and left in scripts/ is not part of the system. This session
    caught that pattern five times inside single modules; run at repo scale it says which whole packages
    are ornaments.

  THRESHOLDS SOMEONE CHOSE. Every comparison against a bare float is a place where a person picked a
    number instead of deriving one, and -- more to the point -- a place a fix made elsewhere cannot reach.
    A quantity that was measured does not land on 0.5 ninety times.

WHAT IT DELIBERATELY DOES NOT COUNT. Integer comparisons are mostly loop bounds and lengths, not
judgements, so only float literals count, and 0.0 / 1.0 are dropped as clamps. Coin flips are separated
out rather than lumped in: `rng.random() < 0.6` inside a genetic operator or a Metropolis acceptance is
correct stochastic search, and calling it a hand-tuned threshold would be a cheap alarm. They are reported
on their own line so a reader can check them, which is how the ones in this repo were cleared.
"""
from __future__ import annotations

import collections
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/perception/macro_audit.json")
SKIP_DIR = {"__pycache__", ".venv", "node_modules", ".git"}
THRESH = re.compile(r"([A-Za-z_][A-Za-z_0-9\.\(\)\[\]'\" ]{0,40}?)\s*[<>]=?\s*(0?\.\d+|[01]\.\d+)")
FLIP = re.compile(r"\b(?:random\(\)|rng\.random\(\)|np\.random\.\w+\(\)?)\s*[<>]=?\s*[0-9.]+")
FAMILY = {
    "score/confidence": ("score", "conf", "prob", "likelihood", "logit", "certain", "belief", "strength"),
    "similarity/match": ("sim", "cos", "dist", "overlap", "iou", "jacc", "match", "align", "corr"),
    "rate/fraction": ("rate", "ratio", "frac", "pct", "percent", "share", "cover", "density",
                      "acc", "recall", "prec", "f1"),
    "energy/hormone": ("energy", "arousal", "valence", "hormone", "stress", "fatigue", "mood", "drive"),
    "time/decay": ("decay", "tau", "half", "age", "elapsed", "ttl", "cool"),
}


def sources(root="packages"):
    for base, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in SKIP_DIR and "test" not in d]
        for f in fs:
            if f.endswith(".py") and "test" not in f and "test" not in base:
                yield os.path.join(base, f)


def thresholds() -> dict:
    per, vals, fam, flips = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for p in sources():
        pkg = p.split(os.sep)[1]
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            if FLIP.search(line) or re.search(r"\br\s*[<>]=?\s*0?\.\d", line):
                flips[pkg] += 1
                continue                        # stochastic search, counted separately and not as a knob
            for lhs, m in THRESH.findall(line):
                if float(m) in (0.0, 1.0):
                    continue
                per[pkg] += 1
                vals[float(m)] += 1
                k = lhs.strip().lower()
                fam[next((n for n, keys in FAMILY.items() if any(x in k for x in keys)),
                         "unclassified")] += 1
    return {"per_package": per, "values": vals, "families": fam, "flips": flips}


def importers(pkg: str) -> int:
    out = subprocess.run(["grep", "-rl", f"packages.{pkg}", "--include=*.py", "packages", "apps",
                          "scripts"], capture_output=True, text=True).stdout
    return len([x for x in out.splitlines()
                if f"{os.sep}{pkg}{os.sep}" not in x.replace("/", os.sep) and "test" not in x])


def main() -> None:
    t = thresholds()
    per, vals, fam, flips = t["per_package"], t["values"], t["families"], t["flips"]
    tot = sum(per.values())
    print(f"HAND-CHOSEN DECISION THRESHOLDS: {tot}  across {len(per)} packages")
    print(f"   (coin flips counted separately: {sum(flips.values())} in {len(flips)} packages -- "
          f"genetic operators, program search, Metropolis acceptance)\n")
    top = vals.most_common(12)
    print("the twelve most repeated values, and their share of every threshold in the system:")
    print("   " + "  ".join(f"{v} x{c}" for v, c in top))
    print(f"   -> {100 * sum(c for _v, c in top) / max(tot, 1):.0f}%   "
          "a measured quantity does not recur\n")
    print(f"{'what is being gated':<24}{'sites':>7}{'share':>8}")
    for k, v in fam.most_common():
        print(f"{k:<24}{v:>7}{100 * v / max(tot, 1):>7.0f}%")
    reach = sum(fam[k] for k in ("score/confidence", "similarity/match", "rate/fraction"))
    print(f"\n-> one calibrated gate would reach {reach} sites, "
          f"{100 * reach / max(tot, 1):.0f}% of the system's judgements\n")

    print(f"{'package':<26}{'thresholds':>11}{'imported by':>13}")
    rows = []
    for k, v in per.most_common(12):
        n = importers(k)
        rows.append({"package": k, "thresholds": v, "importers": n})
        print(f"{k:<26}{v:>11}{n:>13}")

    print("\nORGANS NOTHING IMPORTS -- built, measured, and connected to no consumer:")
    orphan = []
    for d in sorted(os.listdir("packages")):
        if not os.path.isdir(f"packages/{d}") or d in SKIP_DIR:
            continue
        out = subprocess.run(["grep", "-rl", f"packages.{d}", "--include=*.py", "packages", "apps"],
                             capture_output=True, text=True).stdout
        pkgs = [x for x in out.splitlines()
                if f"{os.sep}{d}{os.sep}" not in x.replace("/", os.sep) and "test" not in x]
        if not pkgs:
            s = subprocess.run(["grep", "-rl", f"packages.{d}", "--include=*.py", "scripts"],
                               capture_output=True, text=True).stdout
            orphan.append({"package": d, "scripts_only": len(s.splitlines())})
    for o in sorted(orphan, key=lambda x: -x["scripts_only"])[:15]:
        tag = f"{o['scripts_only']} scripts, 0 packages" if o["scripts_only"] else "nothing at all"
        print(f"   {o['package']:<28}{tag}")
    print(f"   {len(orphan)} of {len([d for d in os.listdir('packages') if os.path.isdir(f'packages/{d}')])} "
          "packages are imported by no other package")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"total": tot, "values": {str(k): v for k, v in vals.items()},
                               "families": dict(fam), "flips": dict(flips),
                               "top_packages": rows, "orphans": orphan}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
