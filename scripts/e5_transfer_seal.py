# -*- coding: utf-8 -*-
"""The E5 transfer seal: freeze B before touching A, and refuse to score if B moved.

    python scripts/e5_transfer_seal.py seal      # BEFORE any A-side work. Writes the seal.
    python scripts/e5_transfer_seal.py check     # has B been touched? (safe to run any time)
    python scripts/e5_transfer_seal.py score     # AFTER the A-side work. Spends the seal.

WHAT A SEAL IS FOR. `docs/ATANOR_E5_transfer_prereg.md` fixes the domains, the metrics and the gate. This
script fixes the STATE: the exact bytes of B's code, the exact numbers B produces today, and the exact
commands that reproduce them. Without that, "B improved" is unfalsifiable -- B's code could drift, its
corpus could be re-cut, its metric could be re-read, and the claim would still be sayable.

THE ONE RULE THE SCRIPT ENFORCES BY ITSELF: if any file on the B list has changed between `seal` and
`score`, the run is VOID. Not penalised, not adjusted -- void. The whole content of E5 is "B improved
WITHOUT BEING TOUCHED", so a B that moved has no measurement left in it.

INCONCLUSIVE COUNTS AS FAIL, the same rule the depth E4 exam runs under. A metric that cannot be
reproduced is not a neutral outcome; it is a missing measurement, and treating it as neutral is how a
seal quietly becomes a formality.

The scorer writes its verdict once. A second `score` on a spent seal writes a diagnostic file instead of
overwriting the verdict -- the mistake that cost the depth exam its first verdict file, fixed there and
inherited here.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SEAL_DIR = Path("data/e5_transfer_seal")
SEAL = SEAL_DIR / "seal.json"
VERDICT = SEAL_DIR / "verdict.json"

# B's code, corpus pointers and evaluation. Any change here voids the run.
B_FILES = [
    "scripts/wiki_property_sweep.py",
    "scripts/run_acquisition_daemon.py",
    "packages/acquisition_daemon/daemon.py",
    "packages/knowledge_acquisition/loop.py",
    "packages/knowledge_acquisition/consensus.py",
    "packages/knowledge_acquisition/evidence.py",
    "packages/atanor_index/retriever.py",
    "data/acquisition_daemon/deficit_questions.txt",
]
# A's file. Changing THIS is the point of the experiment, so it is recorded but never voids.
A_FILES = ["packages/graph_scale/property_extraction.py"]

# measured today, before any A-side work; the seal records them and the scorer re-measures
BASELINE = {
    "B1-yield_facts_per_1k_pages": 91881 / 6899.110,      # 91,881 rows over 6,899,110 pages
    "B1-agree_used_for": 0.471,
    "B1-agree_capable_of": 0.235,
    "B2-queued": 656,
    "B2-pursued": 26349,
}
GATE = {"rise_required_relative": 0.05, "agreement_floor_absolute_drop": 0.02}


def _sha(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception:
        return ""


def seal() -> None:
    if SEAL.exists():
        sys.exit(f"{SEAL} already exists. A seal is cut once; delete it deliberately or read it.")
    SEAL_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "prereg": "docs/ATANOR_E5_transfer_prereg.md",
        "sealed_at_commit": _commit(),
        "baseline": BASELINE,
        "gate": GATE,
        "b_files": {f: _sha(f) for f in B_FILES},
        "a_files": {f: _sha(f) for f in A_FILES},
        "commands": {
            "B1": "python scripts/wiki_property_sweep.py --max-pages 200000",
            "B2": ("python scripts/run_acquisition_daemon.py --local --table --no-curiosity "
                   "--questions data/acquisition_daemon/deficit_questions.txt --batch 600 "
                   "--min-pressure 2 --state data/acquisition_daemon/e5_b2"),
        },
        "rule": "any change to a b_file VOIDS the run; inconclusive counts as FAIL",
        "spent": False,
    }
    SEAL.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    missing = [f for f, h in doc["b_files"].items() if h is None]
    print(f"sealed at {doc['sealed_at_commit'][:12]}")
    print(f"  B files hashed : {sum(1 for h in doc['b_files'].values() if h)} of {len(B_FILES)}")
    if missing:
        print(f"  MISSING        : {missing}")
    print(f"  A files hashed : {list(doc['a_files'])}")
    print(f"  baseline       : {json.dumps(BASELINE)}")
    print(f"wrote {SEAL}")
    print("\nfrom here on, work only in A. Looking at a B metric spends this seal.")


def check() -> dict:
    if not SEAL.exists():
        sys.exit(f"no seal at {SEAL} -- run `seal` first")
    doc = json.loads(SEAL.read_text(encoding="utf-8"))
    moved, same, gone = [], [], []
    for f, h in doc["b_files"].items():
        now = _sha(f)
        if now is None:
            gone.append(f)
        elif now != h:
            moved.append(f)
        else:
            same.append(f)
    a_moved = [f for f, h in doc["a_files"].items() if _sha(f) != h]
    out = {"b_unchanged": len(same), "b_moved": moved, "b_missing": gone,
           "a_changed": a_moved, "valid": not moved and not gone}
    print(f"B unchanged {len(same)}/{len(doc['b_files'])}   "
          f"moved {len(moved)}   missing {len(gone)}")
    if moved:
        print(f"  VOID: these B files changed -> {moved}")
    if a_moved:
        print(f"  A side has changed (expected, this is the experiment): {a_moved}")
    else:
        print("  A side unchanged -- no work done yet, so there is nothing to transfer")
    return out


def score() -> None:
    """Re-measure B and write the verdict once. Requires the caller to supply measured values.

    The scorer deliberately does NOT run B itself: B2 takes about fifty minutes and B1 about two
    hours, so they are run separately and their outputs handed here. What this enforces is the part
    that must not be done by hand -- the void check, the comparison against the sealed baseline, and
    writing the verdict exactly once."""
    if not SEAL.exists():
        sys.exit(f"no seal at {SEAL}")
    doc = json.loads(SEAL.read_text(encoding="utf-8"))
    integrity = check()
    if not integrity["valid"]:
        print("\nVOID -- B moved between seal and score. There is no measurement left in this run.")
        return
    measured_path = SEAL_DIR / "measured.json"
    if not measured_path.exists():
        sys.exit(f"put the re-measured B numbers in {measured_path} first "
                 f"(keys: {sorted(BASELINE)})")
    m = json.loads(measured_path.read_text(encoding="utf-8"))
    base = doc["baseline"]
    gate = doc["gate"]
    rows = []
    for k in sorted(base):
        b, a = base[k], m.get(k)
        if a is None:
            rows.append({"metric": k, "baseline": b, "measured": None, "note": "MISSING"})
            continue
        rel = (a - b) / b if b else 0.0
        rows.append({"metric": k, "baseline": round(b, 4), "measured": round(a, 4),
                     "relative_change": round(rel, 4)})
    missing = [r for r in rows if r.get("note") == "MISSING"]
    yield_rise = max(
        (r["relative_change"] for r in rows
         if r["metric"] in ("B1-yield_facts_per_1k_pages", "B2-queued") and "relative_change" in r),
        default=0.0)
    agree_drop = max(
        (base[k] - m[k] for k in ("B1-agree_used_for", "B1-agree_capable_of") if k in m),
        default=0.0)
    if missing:
        verdict, why = "FAIL", f"inconclusive: {[r['metric'] for r in missing]} not measured"
    elif yield_rise >= gate["rise_required_relative"] and \
            agree_drop <= gate["agreement_floor_absolute_drop"]:
        verdict, why = "PASS", f"yield +{yield_rise:.1%}, agreement drop {agree_drop:.3f}"
    else:
        verdict, why = "FAIL", (f"yield +{yield_rise:.1%} (need "
                                f"+{gate['rise_required_relative']:.0%}), "
                                f"agreement drop {agree_drop:.3f}")
    out = {"verdict": verdict, "why": why, "rows": rows,
           "sealed_at_commit": doc["sealed_at_commit"], "scored_at_commit": _commit(),
           "b_untouched": True, "gate": gate}
    target = VERDICT if not VERDICT.exists() else SEAL_DIR / f"verdict_diagnostic_{_commit()[:8]}.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    doc["spent"] = True
    SEAL.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"\n{verdict}: {why}")
    for r in rows:
        print(f"   {r['metric']:<34} {r.get('baseline')} -> {r.get('measured')}  "
              f"{r.get('relative_change', r.get('note', ''))}")
    print(f"wrote {target}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"seal": seal, "check": check, "score": score}.get(cmd, check)()
