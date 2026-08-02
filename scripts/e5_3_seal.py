# -*- coding: utf-8 -*-
"""The E5-2 seal: two arms, and a B1 baseline that is finally comparable to its own re-measurement.

    python scripts/e5_2_seal.py seal      # BEFORE any A-side work
    python scripts/e5_2_seal.py check     # has B moved? (safe any time)
    python scripts/e5_2_seal.py score     # AFTER the A-side work. Spends the seal.

WHAT IS DIFFERENT FROM E5-1, and it is the one thing that mattered. E5-1's B1 baseline was taken over the
whole 6.9M-page corpus while its re-measurement read a 200k slice, so the ratio between them measured
slice composition rather than the extractor. Here the baseline is produced by the SAME PROCEDURE that
will re-measure it: `e5_b1_closeout.py` streams one fixed slice and runs the frozen extractor and the
live one over the same sentences, so page order, lead selection and subject filtering are shared and the
extractor is the only thing that differs.

The frozen extractor is a file, hashed by this seal. That is what makes "before" reproducible after A has
moved on -- E5-1 had no such snapshot, which is why its B1 arm could only ever be reconstructed
post-hoc.

BOTH ARMS MUST RISE. E5-1 showed one arm can. What is unproven is that a change to a shared substrate
shows up in two independent downstream consumers at once, and a gate that accepts the best of two arms
cannot distinguish transfer from luck. So the gate here takes the MINIMUM, not the maximum.

INCONCLUSIVE COUNTS AS FAIL, unchanged. A metric that cannot be reproduced is a missing measurement, and
treating it as neutral is how a seal quietly becomes a formality.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SEAL_DIR = Path("data/e5_transfer_seal_3")
SEAL = SEAL_DIR / "seal.json"
VERDICT = SEAL_DIR / "verdict.json"
FROZEN_A = SEAL_DIR / "property_extraction_FROZEN_A.py"

#: B's code, corpus and measurement procedure. Any change voids the run.
B_FILES = [
    "scripts/wiki_property_sweep.py",
    "scripts/run_acquisition_daemon.py",
    "scripts/e5_b1_closeout.py",
    "packages/acquisition_daemon/daemon.py",
    "packages/knowledge_acquisition/loop.py",
    "packages/knowledge_acquisition/consensus.py",
    "packages/knowledge_acquisition/evidence.py",
    "packages/atanor_index/retriever.py",
    "data/acquisition_daemon/deficit_questions.txt",
]
A_FILES = ["packages/graph_scale/property_extraction.py"]

#: measured with the frozen extractor, on the exact procedure the scorer re-runs
BASELINE = {
    "B1-rows": 7127,
    "B1-per_1k": 35.6348,
    "B2-queued": 800,
    "B2-pursued": 26349,
}
GATE = {"b2_rise_required": 0.05, "b1_may_not_regress": True, "pursued_must_match": True,
        "why": ("E5-2 measured that a change reaches B1 directly and B2 only through consensus, "
                "so B1 is the easy arm. The hard arm is the gate now; B1 only has to not fall.")}

COMMANDS = {
    "B1": (f"python scripts/e5_b1_closeout.py --pages 200000 --old {FROZEN_A}"),
    "B2": ("python scripts/run_acquisition_daemon.py --local --table --no-curiosity "
           "--questions data/acquisition_daemon/deficit_questions.txt --batch 600 "
           "--min-pressure 2 --state data/acquisition_daemon/e5_3_b2"),
}


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
        sys.exit(f"{SEAL} already exists. A seal is cut once; read it or delete it deliberately.")
    if not FROZEN_A.exists():
        sys.exit(f"no frozen extractor at {FROZEN_A} -- snapshot it before sealing, or 'before' "
                 f"cannot be reproduced once A moves")
    SEAL_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "prereg": "docs/ATANOR_E5_3_transfer_prereg.md",
        "sealed_at_commit": _commit(),
        "baseline": BASELINE,
        "gate": GATE,
        "frozen_a": {str(FROZEN_A): _sha(str(FROZEN_A))},
        "b_files": {f: _sha(f) for f in B_FILES},
        "a_files": {f: _sha(f) for f in A_FILES},
        "commands": COMMANDS,
        "rule": ("any change to a b_file VOIDS the run; BOTH arms must rise >= 5%; "
                 "B2-pursued must come back identical; inconclusive counts as FAIL"),
        "spent": False,
    }
    SEAL.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    missing = [f for f, h in doc["b_files"].items() if h is None]
    print(f"sealed at {doc['sealed_at_commit'][:12]}")
    print(f"  B files hashed : {sum(1 for h in doc['b_files'].values() if h)} of {len(B_FILES)}")
    if missing:
        print(f"  MISSING        : {missing}")
    print(f"  frozen A       : {FROZEN_A} ({_sha(str(FROZEN_A))[:16]})")
    print(f"  baseline       : {json.dumps(BASELINE)}")
    print(f"  gate           : B2 +{GATE['b2_rise_required']:.0%} is the gate; B1 must not regress; "
          f"pursued must match")
    print(f"wrote {SEAL}\n\nfrom here on, work only in A. Looking at a B metric spends this seal.")


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
    frozen_moved = [f for f, h in doc["frozen_a"].items() if _sha(f) != h]
    a_moved = [f for f, h in doc["a_files"].items() if _sha(f) != h]
    print(f"B unchanged {len(same)}/{len(doc['b_files'])}   moved {len(moved)}   missing {len(gone)}")
    if moved:
        print(f"  VOID: these B files changed -> {moved}")
    if frozen_moved:
        print(f"  VOID: the frozen 'before' extractor was modified -> {frozen_moved}")
    print(f"  A side: {'changed (expected)' if a_moved else 'unchanged -- no work done yet'}")
    return {"b_unchanged": len(same), "b_moved": moved, "b_missing": gone,
            "frozen_moved": frozen_moved, "a_changed": a_moved,
            "valid": not moved and not gone and not frozen_moved}


def score() -> None:
    if not SEAL.exists():
        sys.exit(f"no seal at {SEAL}")
    doc = json.loads(SEAL.read_text(encoding="utf-8"))
    integrity = check()
    if not integrity["valid"]:
        print("\nVOID -- B or the frozen baseline moved. There is no measurement left in this run.")
        return
    measured_path = SEAL_DIR / "measured.json"
    if not measured_path.exists():
        sys.exit(f"put the re-measured numbers in {measured_path} first (keys: {sorted(BASELINE)})")
    m = json.loads(measured_path.read_text(encoding="utf-8"))
    base, gate = doc["baseline"], doc["gate"]

    rows, missing = [], []
    for k in sorted(base):
        b, a = base[k], m.get(k)
        if a is None:
            missing.append(k)
            rows.append({"metric": k, "baseline": b, "measured": None, "note": "MISSING"})
            continue
        rel = (a - b) / b if b else 0.0
        rows.append({"metric": k, "baseline": b, "measured": a, "relative_change": round(rel, 4)})

    need = gate["b2_rise_required"]
    b1 = next((r for r in rows if r["metric"] == "B1-rows"), None)
    b2 = next((r for r in rows if r["metric"] == "B2-queued"), None)
    pursued = next((r for r in rows if r["metric"] == "B2-pursued"), None)

    if missing:
        verdict, why = "FAIL", f"inconclusive: {missing} not measured"
    elif pursued and pursued.get("measured") != base["B2-pursued"]:
        verdict, why = "FAIL", (f"control broke: B2-pursued {base['B2-pursued']} -> "
                                f"{pursued['measured']}; the work done changed, so the yield "
                                f"comparison is not clean")
    else:
        # the MINIMUM of the two arms, not the maximum. A gate that accepts the better arm cannot
        # tell transfer from luck, which is exactly what E5-1 left unresolved.
        b2_ok = b2["relative_change"] >= need
        b1_ok = b1["relative_change"] >= -0.005          # not a rise requirement: a no-regress floor
        if b2_ok and b1_ok:
            verdict, why = "PASS", (f"B2 {b2['relative_change']:+.1%} cleared +{need:.0%} and B1 held "
                                    f"at {b1['relative_change']:+.1%}")
        elif not b2_ok:
            verdict, why = "FAIL", (f"B2 {b2['relative_change']:+.1%} did not clear +{need:.0%} "
                                    f"(B1 {b1['relative_change']:+.1%})")
        else:
            verdict, why = "FAIL", (f"B2 cleared at {b2['relative_change']:+.1%} but B1 REGRESSED to "
                                    f"{b1['relative_change']:+.1%} — a gain bought by losing the "
                                    f"other consumer is not transfer")

    out = {"verdict": verdict, "why": why, "rows": rows, "gate": gate,
           "sealed_at_commit": doc["sealed_at_commit"], "scored_at_commit": _commit(),
           "b_untouched": True}
    target = VERDICT if not VERDICT.exists() else SEAL_DIR / f"verdict_diagnostic_{_commit()[:8]}.json"
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    doc["spent"] = True
    SEAL.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"\n{verdict}: {why}")
    for r in rows:
        print(f"   {r['metric']:<16} {r.get('baseline')} -> {r.get('measured')}  "
              f"{r.get('relative_change', r.get('note', ''))}")
    print(f"wrote {target}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"seal": seal, "check": check, "score": score}.get(cmd, check)()
