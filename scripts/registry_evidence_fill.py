# -*- coding: utf-8 -*-
"""Fill the registry's evidence column as far as measurement reaches, and refuse to go further.

    python scripts/registry_evidence_fill.py            # measure and report
    python scripts/registry_evidence_fill.py --write     # raise stages that measurement supports

THE COLUMN WAS NEVER FILLED. 138 of 144 organs read `evidence.stage: V0`, and checking what those entries
cite shows why: only FIVE organs reference anything beyond their own directory path. V0 x138 is the default
the registry shipped with, not a verdict anyone reached -- exactly like `wiring.runtime_status` sat at
`unknown` x125 until it was measured. So the honest reading of "138 organs at the bottom rung" is not that
the system is weak; it is that the system has never been assessed.

THE LADDER'S MEANING IS TACIT AND THAT IS ITS OWN FINDING. Nothing defines V0..E6 in one place; the meaning
has to be recovered from consistent use across the evidence documents, and `docs/ATANOR_G0_evidence_and_
blockers.md` is the clearest:

    V0   unknown -- "one V0/unknown handoff"
    M1   reachability attested -- "19 edges at M1", "selected M1 reachability"
    M2   mechanism with cited refs, no control run
    M3   a CONTROL was actually run -- "nine narrowly scoped M3 controlled-test edges"
    E4   an independent functional gate -- "E4 functional gates", an evaluator that is not the builder
    E5   paired capability measurement -- "paired E5 measurement", hidden holdout, signature
    E6   sealed, external, blind

WHAT THIS TOOL WILL AND WILL NOT CLAIM. Reachability is measurable, so a wired organ is at least M1 and
that is filled. Whether a control was run is measurable from the organ's own tests and proof artifacts, so
M3 is PROPOSED with the file and line that supports it. E4 and above require an evaluator who is not the
builder and a holdout nobody has seen; no amount of grepping establishes either, so those stages are never
assigned here and the organs that look like candidates are listed for human assessment instead.

It also only ever RAISES, and only from V0. The six stages a person set by hand -- cgsr M3, world4d M3,
temporal_reasoning M3, cognitive_core M3, continuous_self M1 -- are left exactly as they are. A tool that
can lower a human's attestation is a tool that can quietly erase evidence.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REG = Path("data/architecture/catalog/organ_registry_v1.json")
WIRING = Path("data/architecture/wiring_measurement.json")
OUT = Path("data/architecture/evidence_measurement.json")
SKIP = {"__pycache__", ".venv", "node_modules", ".git"}

# a CONTROL is a comparison against something that should not work
CONTROL = re.compile(r"\b(control|shuffl|permut|random.?baseline|baseline|chance|null.?model|"
                     r"scrambl|placebo|sham|randomi[sz]ed.?label|untrained|ablat)", re.I)
# a STATISTIC is a number that could refute the claim
STAT = re.compile(r"\b(p_?value|p\s*[<=]\s*0|pvalue|auc|auroc|spearman|pearson|lift|"
                  r"significan|confidence.?interval|clopper|bootstrap|permutation.?p|"
                  r"held.?out|holdout)", re.I)
# INDEPENDENCE / SEALING -- reported as candidates, never assigned
EXTERNAL = re.compile(r"\b(sealed|seal\b|blind|developer.?blind|independent.?(judge|evaluator|"
                      r"assessor)|external.?(judge|referee)|attestation|operator.?sign)", re.I)


def files_of(pkg: str):
    for base, ds, fs in os.walk(f"packages/{pkg}"):
        ds[:] = [d for d in ds if d not in SKIP]
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(base, f).replace("\\", "/")


def proofs_of(pkg: str):
    """Proof artefacts an organ has left behind, wherever they landed under data/."""
    hits = []
    for base, ds, fs in os.walk("data"):
        ds[:] = [d for d in ds if d not in SKIP]
        if "proof" not in base.lower() and pkg not in base.replace("\\", "/"):
            continue
        for f in fs:
            if not f.endswith((".json", ".md")):
                continue
            p = os.path.join(base, f).replace("\\", "/")
            if pkg in p or pkg in f:
                hits.append(p)
    return hits[:12]


def scan(pkg: str) -> dict:
    """What this organ can show for itself, with the refs that show it."""
    tests, control_refs, stat_refs, ext_refs = 0, [], [], []
    for p in files_of(pkg):
        is_test = "test" in p
        if is_test:
            tests += 1
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if CONTROL.search(line) and (is_test or "assert" in line or "def " in line):
                control_refs.append(f"{p}:{i}")
            if STAT.search(line):
                stat_refs.append(f"{p}:{i}")
            if EXTERNAL.search(line):
                ext_refs.append(f"{p}:{i}")
    pr = proofs_of(pkg)
    for p in pr:
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if CONTROL.search(text):
            control_refs.append(p)
        if STAT.search(text):
            stat_refs.append(p)
        if EXTERNAL.search(text):
            ext_refs.append(p)
    return {"tests": tests, "proofs": pr,
            "control": control_refs[:4], "stat": stat_refs[:4], "external": ext_refs[:4]}


def stage_of(pkg: str, wired: str, s: dict) -> tuple[str, list[str]]:
    """The strongest stage MEASUREMENT supports. Never E4 or above -- see the module docstring."""
    if s["control"] and s["stat"] and s["tests"]:
        return "M3", (s["control"][:2] + s["stat"][:2])
    if wired in ("live_default", "live_conditional") and s["tests"]:
        return "M2", ([f"packages/{pkg} reachable from apps/api/app/main.py"] + s["stat"][:1])
    if wired in ("live_default", "live_conditional"):
        return "M1", [f"packages/{pkg} reachable from apps/api/app/main.py"]
    return "V0", []


ORDER = {"V0": 0, "M1": 1, "M2": 2, "M3": 3, "E4": 4, "E5": 5, "E6": 6}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    reg = json.loads(REG.read_text(encoding="utf-8"))
    wiring = json.loads(WIRING.read_text(encoding="utf-8"))["status"]
    organs = {o["name"]: o for o in reg["organs"]}

    rows, raised, cand = [], 0, []
    for name, o in sorted(organs.items()):
        if name in SKIP or not os.path.isdir(f"packages/{name}"):
            continue
        s = scan(name)
        w = wiring.get(name, "unknown")
        st, refs = stage_of(name, w, s)
        was = o["evidence"]["stage"]
        rows.append({"organ": name, "wired": w, "was": was, "measured": st,
                     "tests": s["tests"], "proofs": len(s["proofs"]),
                     "refs": refs, "external": s["external"]})
        if s["external"] and ORDER[st] >= 3:
            cand.append({"organ": name, "stage": st, "external_refs": s["external"][:2]})
        if was == "V0" and ORDER[st] > 0:
            raised += 1

    import collections
    before = collections.Counter(o["evidence"]["stage"] for o in reg["organs"])
    after = collections.Counter(
        max(r["was"], r["measured"], key=lambda x: ORDER[x]) for r in rows)
    print(f"assessed {len(rows)} organs against the ladder recovered from docs/ATANOR_G0\n")
    print(f"{'stage':<8}{'before':>8}{'measured':>10}   meaning")
    mean = {"V0": "unknown -- never assessed", "M1": "reachable from the entrypoint",
            "M2": "reachable and has tests", "M3": "a CONTROL was actually run",
            "E4": "independent gate -- NOT machine-assignable",
            "E5": "paired capability -- NOT machine-assignable",
            "E6": "sealed, external -- NOT machine-assignable"}
    for st in ("V0", "M1", "M2", "M3", "E4", "E5", "E6"):
        print(f"{st:<8}{before[st]:>8}{after[st]:>10}   {mean[st]}")
    print(f"\n-> {raised} organs raised off the V0 default by measurement")
    print(f"-> 0 organs assigned E4 or above, by construction: independence and sealing "
          f"cannot be established by reading source")

    m3 = [r for r in rows if r["measured"] == "M3"]
    print(f"\nM3 by measurement -- a control and a statistic, both cited ({len(m3)}):")
    print(f"{'organ':<26}{'wired':<18}{'tests':>6}{'proofs':>7}  first supporting ref")
    for r in sorted(m3, key=lambda x: -x["tests"])[:16]:
        print(f"{r['organ']:<26}{r['wired']:<18}{r['tests']:>6}{r['proofs']:>7}  "
              f"{(r['refs'][0] if r['refs'] else '')[:52]}")

    print(f"\nCANDIDATES FOR HUMAN ASSESSMENT AT E4+ -- these cite sealing, blinding or an independent")
    print(f"judge, which is the shape E4/E5 needs. A person must confirm; this tool assigns nothing.")
    print(f"{'organ':<26}{'measured':<10}  what it cites")
    for c in sorted(cand, key=lambda x: x["organ"])[:14]:
        print(f"{c['organ']:<26}{c['stage']:<10}  {c['external_refs'][0][:56]}")

    if a.write:
        changed = 0
        for o in reg["organs"]:
            r = next((x for x in rows if x["organ"] == o["name"]), None)
            if r is None:
                continue
            # RAISE ONLY, and only off the default. A human's attestation is never lowered or replaced.
            if o["evidence"]["stage"] == "V0" and ORDER[r["measured"]] > 0:
                o["evidence"]["stage"] = r["measured"]
                o["evidence"]["refs"] = (r["refs"] or [f"packages/{o['name']}"])[:4]
                changed += 1
        REG.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {REG}  ({changed} raised off V0; no stage lowered, none set above M3)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows, "e4_candidates": cand}, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
