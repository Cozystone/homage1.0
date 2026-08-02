# -*- coding: utf-8 -*-
"""Every package with the evidence needed to judge it: size, consumers, age, and whether it still moves.

    python scripts/package_inventory.py

The macro audit found 43 packages that no other package imports. The owner's correction is the right one:
some of those are not unwired, they are SUPERSEDED -- built before a better structure existed, and wiring
them now would drag dead architecture back into the live system. Telling the two apart needs evidence, so
this collects it before anything is judged.

FOUR SIGNALS, none of them decisive alone:

    consumers   how many packages and apps import it. Zero means it is not part of the system today.
    last touch  the newest commit touching any of its files. A package with consumers that has not moved
                in months is stable; one with NO consumers that has not moved is a candidate for retirement.
    first touch with the last touch it gives a lifespan -- built and abandoned in one day reads very
                differently from built, used, and left alone.
    size        a large orphan is a real decision; a fifty-line orphan is a rounding error.

WHAT THIS DELIBERATELY DOES NOT DO is decide. Retirement is the owner's call and deleting a package on a
heuristic is exactly the kind of irreversible act that should never run off a script's opinion. The output
is an inventory, sorted so the decisions that matter are at the top.
"""
from __future__ import annotations

import collections
import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/perception/package_inventory.json")
SKIP = {"__pycache__", ".venv", "node_modules", ".git"}
NOW = None          # filled from the newest commit in the repo, so nothing depends on the wall clock


def git_touch() -> dict:
    """(first, last) commit unix time per package, from one pass over the whole history."""
    raw = subprocess.run(["git", "log", "--format=%x00%at", "--name-only"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    first, last = {}, {}
    for chunk in raw.split("\x00"):
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        if not lines:
            continue
        try:
            t = float(lines[0])
        except ValueError:
            continue
        for path in lines[1:]:
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 1 and parts[0] == "packages":
                p = parts[1]
                last[p] = max(last.get(p, 0.0), t)
                first[p] = min(first.get(p, 9e18), t)
    return first, last


def consumers(pkg: str):
    """Modules outside the package that import it, split by where they live."""
    out = subprocess.run(["grep", "-rl", f"packages.{pkg}", "--include=*.py",
                          "packages", "apps", "scripts"],
                         capture_output=True, text=True).stdout
    rows = [x.replace("\\", "/") for x in out.splitlines() if f"/{pkg}/" not in x.replace("\\", "/")]
    real = [x for x in rows if "test" not in x and not x.startswith("scripts/")]
    scr = [x for x in rows if x.startswith("scripts/")]
    return real, scr


def main() -> None:
    global NOW
    first, last = git_touch()
    NOW = max(last.values()) if last else 0.0
    rows = []
    for d in sorted(os.listdir("packages")):
        base = os.path.join("packages", d)
        if not os.path.isdir(base) or d in SKIP:
            continue
        loc, nfiles, tests = 0, 0, 0
        for r, ds, fs in os.walk(base):
            ds[:] = [x for x in ds if x not in SKIP]
            for f in fs:
                if not f.endswith(".py"):
                    continue
                try:
                    n = len(io.open(os.path.join(r, f), encoding="utf-8", errors="replace").readlines())
                except OSError:
                    continue
                if "test" in f or "test" in r:
                    tests += 1
                else:
                    nfiles += 1
                    loc += n
        real, scr = consumers(d)
        rows.append({"package": d, "loc": loc, "files": nfiles, "tests": tests,
                     "consumers": len(real), "script_only": len(scr),
                     "last_days": round((NOW - last.get(d, NOW)) / 86400.0, 1),
                     "life_days": round((last.get(d, 0) - first.get(d, 0)) / 86400.0, 1)})

    live = [r for r in rows if r["consumers"] > 0]
    orph = [r for r in rows if r["consumers"] == 0]
    print(f"{len(rows)} packages   {sum(r['loc'] for r in rows):,} lines")
    print(f"   {len(live)} have a consumer   ({sum(r['loc'] for r in live):,} lines)")
    print(f"   {len(orph)} have none        ({sum(r['loc'] for r in orph):,} lines, "
          f"{100 * sum(r['loc'] for r in orph) / max(sum(r['loc'] for r in rows), 1):.0f}% of the code)\n")

    print("ORPHANS, largest first -- these are the decisions that matter")
    print(f"{'package':<26}{'lines':>7}{'files':>6}{'tests':>6}{'scripts':>8}"
          f"{'idle d':>8}{'life d':>8}")
    for r in sorted(orph, key=lambda x: -x["loc"])[:26]:
        print(f"{r['package']:<26}{r['loc']:>7}{r['files']:>6}{r['tests']:>6}"
              f"{r['script_only']:>8}{r['last_days']:>8.0f}{r['life_days']:>8.0f}")

    one_day = [r for r in orph if r["life_days"] < 1.0]
    print(f"\n   of the orphans, {len(one_day)} were built and last touched within a single day "
          f"({sum(r['loc'] for r in one_day):,} lines) -- built for one experiment and left")
    stale = [r for r in orph if r["last_days"] > 14]
    print(f"   {len(stale)} have not been touched in over two weeks ({sum(r['loc'] for r in stale):,} lines)")

    print(f"\nMOST-DEPENDED-ON PACKAGES -- whatever the final structure is, it is built from these")
    print(f"{'package':<26}{'lines':>7}{'consumers':>11}{'idle d':>8}")
    for r in sorted(live, key=lambda x: -x["consumers"])[:18]:
        print(f"{r['package']:<26}{r['loc']:>7}{r['consumers']:>11}{r['last_days']:>8.0f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
