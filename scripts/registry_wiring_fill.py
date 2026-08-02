# -*- coding: utf-8 -*-
"""Fill the organ registry's wiring column from the real import graph, and name the archive candidates.

    python scripts/registry_wiring_fill.py            # measure and report
    python scripts/registry_wiring_fill.py --write    # also write runtime_status into the registry

THE FINAL STRUCTURE ALREADY EXISTS. data/architecture/catalog/organ_registry_v1.json carries 130 organs
with exactly the fields the question needs -- lifecycle, canonical_domain, built, wiring, authority,
evidence -- and its judgement columns are blank: 125 of 130 have wiring.runtime_status "unknown", and the
`archive` lifecycle that the enum has always allowed has never once been used. So nothing here invents an
architecture. It fills in the one that is already declared, from measurement.

WIRED MEANS REACHABLE, NOT MENTIONED. An earlier pass counted importers with grep and called the zero-count
packages orphans, which is wrong in both directions: a package imported only by a script is not wired, and
a package imported by something that is itself unreachable is not wired either. So the import graph is
built with ast and walked transitively from the application entrypoint. A package is live when the running
program can actually reach it.

    live_default       reachable from apps/api/app/main.py
    live_conditional   imported by a non-test package, but not reachable from the entrypoint
    test_only          nothing but tests import it
    unwired            nothing but scripts import it, or nothing at all

AND BEING UNWIRED IS NOT A VERDICT. Three kinds of package sit at zero consumers and they need opposite
treatment, which the registry's own lifecycle enum already distinguishes:

    fixture   an INSTRUMENT -- a benchmark, a probe, a proof harness. Importing a measuring device into the
              runtime would be the defect; zero consumers is correct and permanent for these.
    archive   SUPERSEDED -- built before a better structure existed. Wiring it would drag dead architecture
              back in. This script only NOMINATES; retirement is the owner's decision and no file is deleted.
    canonical a real organ that is genuinely not connected yet, which is the only case that calls for wiring.

The nominations carry their evidence -- lifespan, idle time, test count, and what the package says it is --
because "this looks obsolete" is not a reason to remove anything.
"""
from __future__ import annotations

import ast
import collections
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REG = Path("data/architecture/catalog/organ_registry_v1.json")
OUT = Path("data/architecture/wiring_measurement.json")
ROOTS = ("apps/api/app/main.py",)
SKIP = {"__pycache__", ".venv", "node_modules", ".git"}
INSTRUMENT = re.compile(r"proof-only|benchmark|bench\b|probe|instrument|harness|battery|exam|"
                        r"holdout|validator|audit", re.I)


def py_files(*roots):
    for root in roots:
        for base, ds, fs in os.walk(root):
            ds[:] = [d for d in ds if d not in SKIP]
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(base, f).replace("\\", "/")


def imports_of(path: str):
    """Packages referenced by this file, via ast so a mention inside a string or comment does not count."""
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return set()
    out = set()
    for n in ast.walk(tree):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods = [n.module]
        for m in mods:
            p = m.split(".")
            if len(p) >= 2 and p[0] == "packages":
                out.add(p[1])
    return out


def build_graph():
    """file -> packages it imports, plus package -> files inside it, for transitive reachability."""
    fimp, pkg_files = {}, collections.defaultdict(list)
    for f in py_files("packages", "apps", "scripts"):
        fimp[f] = imports_of(f)
        parts = f.split("/")
        if parts[0] == "packages" and len(parts) > 2:
            pkg_files[parts[1]].append(f)
    return fimp, pkg_files


def reachable(fimp, pkg_files):
    """Packages the entrypoint can actually get to, following imports through packages as it goes."""
    seen, front = set(), []
    for r in ROOTS:
        if os.path.exists(r):
            front.extend(fimp.get(r.replace("\\", "/"), set()))
    while front:
        p = front.pop()
        if p in seen:
            continue
        seen.add(p)
        for f in pkg_files.get(p, []):
            front.extend(x for x in fimp[f] if x not in seen)
    return seen


def classify(pkg, fimp, pkg_files, live):
    if pkg in live:
        return "live_default"
    outside = [f for f, imps in fimp.items() if pkg in imps and f"/{pkg}/" not in f]
    real = [f for f in outside if "test" not in f and not f.startswith("scripts/")]
    tests = [f for f in outside if "test" in f]
    scripts = [f for f in outside if f.startswith("scripts/")]
    if real:
        return "live_conditional"
    if tests and not scripts:
        return "test_only"
    return "unwired"


def docline(pkg: str) -> str:
    best = ""
    for base, ds, fs in os.walk(f"packages/{pkg}"):
        ds[:] = [d for d in ds if d not in SKIP and "test" not in d]
        for f in fs:
            if not f.endswith(".py") or "test" in f:
                continue
            try:
                t = ast.get_docstring(ast.parse(
                    io.open(os.path.join(base, f), encoding="utf-8", errors="replace").read()))
            except (OSError, SyntaxError):
                continue
            if t:
                s = " ".join(t.strip().splitlines()[0].split())
                if len(s) > len(best):
                    best = s
    return best[:96]


def main() -> None:
    write = "--write" in sys.argv
    reg = json.loads(REG.read_text(encoding="utf-8"))
    organs = {o["name"]: o for o in reg["organs"]}
    inv = {r["package"]: r for r in json.loads(
        Path("data/perception/package_inventory.json").read_text(encoding="utf-8"))}

    fimp, pkg_files = build_graph()
    live = reachable(fimp, pkg_files)
    all_pkgs = sorted(d for d in os.listdir("packages") if os.path.isdir(f"packages/{d}"))
    status = {p: classify(p, fimp, pkg_files, live) for p in all_pkgs}

    c = collections.Counter(status.values())
    print(f"import graph: {len(fimp)} files, entrypoint {ROOTS[0]}")
    print(f"MEASURED wiring across {len(all_pkgs)} packages")
    for k in ("live_default", "live_conditional", "test_only", "unwired"):
        print(f"   {k:<20}{c[k]:>4}")
    print(f"\n   the registry currently says: "
          f"{dict(collections.Counter(o['wiring']['runtime_status'] for o in reg['organs']))}")
    print(f"   packages absent from the registry: "
          f"{len([p for p in all_pkgs if p not in organs])}")

    unw = [p for p in all_pkgs if status[p] == "unwired" and p != "__pycache__"]
    # THE DECLARED LIFECYCLE OUTRANKS MY KEYWORD. A first pass classified instruments by searching
    # docstrings for words like "probe" and "audit", and it swallowed co_allocator -- the
    # Conscious-Orchestrator effort allocator, declared `canonical`, an organ and not a measuring device.
    # The registry already records what each package IS; reading that is evidence, and guessing from
    # vocabulary is the same keyword shortcut operator_census was written to warn against.
    fixt = [p for p in unw
            if organs.get(p, {}).get("lifecycle") == "fixture"
            or (organs.get(p, {}).get("lifecycle") != "canonical"
                and INSTRUMENT.search(docline(p) or ""))]
    print(f"\nUNWIRED: {len(unw)} packages. Splitting them by what they ARE, not by their consumer count.")
    print(f"\n  INSTRUMENTS -- zero consumers is correct and permanent ({len(fixt)})")
    print(f"  {'package':<24}{'lifecycle':<11}{'domain':<24}{'lines':>6}")
    for p in sorted(fixt, key=lambda x: -inv.get(x, {}).get("loc", 0)):
        o = organs.get(p, {})
        print(f"  {p:<24}{o.get('lifecycle', '-'):<11}{o.get('canonical_domain', '-'):<24}"
              f"{inv.get(p, {}).get('loc', 0):>6}")

    rest = [p for p in unw if p not in fixt]
    oneday = [p for p in rest if inv.get(p, {}).get("life_days", 99) < 1.0
              and inv.get(p, {}).get("last_days", 0) > 3]
    print(f"\n  ARCHIVE CANDIDATES -- built and abandoned inside one day, idle since ({len(oneday)})")
    print(f"  {'package':<24}{'lines':>6}{'idle d':>8}{'tests':>6}  what it says it is")
    for p in sorted(oneday, key=lambda x: -inv.get(x, {}).get("loc", 0)):
        r = inv.get(p, {})
        print(f"  {p:<24}{r.get('loc', 0):>6}{r.get('last_days', 0):>8.0f}{r.get('tests', 0):>6}  "
              f"{docline(p)[:60]}")
    print("   NOMINATED ONLY. Nothing is deleted and no lifecycle is changed to archive by this script.")

    todo = [p for p in rest if p not in oneday]
    print(f"\n  GENUINELY UNWIRED ORGANS -- the only group that calls for wiring ({len(todo)})")
    print(f"  {'package':<24}{'lines':>6}{'idle d':>8}  what it says it is")
    for p in sorted(todo, key=lambda x: -inv.get(x, {}).get("loc", 0)):
        r = inv.get(p, {})
        print(f"  {p:<24}{r.get('loc', 0):>6}{r.get('last_days', 0):>8.0f}  {docline(p)[:60]}")

    if write:
        changed = 0
        for o in reg["organs"]:
            s = status.get(o["name"])
            if s and o["wiring"]["runtime_status"] != s:
                o["wiring"]["runtime_status"] = s
                o["wiring"].setdefault("refs", [])
                o["wiring"]["refs"] = ["scripts/registry_wiring_fill.py (measured from the import graph)"]
                changed += 1
        for p in all_pkgs:
            if p not in organs:
                reg["organs"].append({
                    "name": p, "path": f"packages/{p}", "lifecycle": "shadow",
                    "canonical_domain": "platform",
                    "built": {"status": True, "refs": [f"packages/{p}"]},
                    "wiring": {"runtime_status": status[p],
                               "refs": ["scripts/registry_wiring_fill.py"]},
                    "authority": {"level": "none", "refs": []},
                    "evidence": {"stage": "V0", "refs": [f"packages/{p}"]}})
                changed += 1
        reg["organs"].sort(key=lambda o: o["name"])
        REG.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {REG}  ({changed} entries filled; lifecycle untouched)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"status": status, "instruments": fixt,
                               "archive_candidates": oneday, "to_wire": todo}, indent=2),
                   encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
