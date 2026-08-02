# -*- coding: utf-8 -*-
"""B5-E2E aggregate verdict — the REAL-body re-test after the spec author's audit.

All three missions now run against the actual system with the answer keys sealed behind honeypots:
  B5-1-E2E  real realize_dual composer, route = composer telemetry, coercion injected
  B5-2-E2E  real bitemporal store (as_of fixed), OUT-OF-PROCESS independent oracle
  B5-3-E2E  planner REASONS over raw triples (no pre-computed booleans)
Every executor is wrapped in a SealedCase; any answer-key access -> cortisol guilt + voided verdict.
Still out of scope (honestly): retrieval against the frozen 141M store, 3B/8B baseline, human fluency.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from packages.b5_missions import e2e_incident, e2e_memory, e2e_recovery

ROOT = Path(__file__).resolve().parents[2]


def _run(fn) -> tuple[bool, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        passed = bool(fn())                              # STRUCTURED verdict (audit #7): the runner
    return passed, buf.getvalue()                        # returns its gate result; stdout is display


def main() -> None:
    print("=" * 78)
    print("ATANOR B5-E2E -- real-body re-test (answer keys sealed, honeypot-guarded)")
    print("=" * 78)
    results = {}
    for label, fn in [("B5-1-E2E incident (real composer)", e2e_incident.main),
                      ("B5-2-E2E memory (out-of-proc oracle)", e2e_memory.main),
                      ("B5-3-E2E recovery (raw-triple reasoning)", e2e_recovery.main)]:
        ok, out = _run(fn)
        results[label] = ok
        print(out.rstrip())
        print("-" * 78)
    b5_e2e = all(results.values())
    print("B5-E2E SUMMARY")
    for k, v in results.items():
        print(f"  {k:42s} {'PASS' if v else 'FAIL'}")
    print(f"\nB5-E2E VERDICT: {'PASS (all three, real body, answer keys sealed)' if b5_e2e else 'FAIL'}")
    print("STILL NOT RUN (honest): 141M-store retrieval stage; 3B/8B baseline; human blind fluency.")
    # bind the verdict to the exact code + report bytes (audit: evidence must be hash-bound)
    git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             cwd=str(ROOT)).stdout.strip()
    report_hashes = {}
    for name in ("b5_1_e2e_report.json", "b5_2_e2e_report.json", "b5_3_e2e_report.json"):
        fp = ROOT / "data" / "b5_missions" / name
        if fp.exists():
            report_hashes[name] = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    (ROOT / "data" / "b5_missions" / "b5_e2e_verdict.json").write_text(
        json.dumps({"missions": results, "b5_e2e_pass": b5_e2e, "git_sha": git_sha,
                    "report_sha256_16": report_hashes,
                    "still_not_run": ["141M_retrieval", "live_prompt_path", "3B_8B_baseline",
                                       "human_fluency", "sealed_private_holdout"]}, indent=2),
        encoding="utf-8")
    print(f"verdict bound to git {git_sha[:12]} + report hashes {list(report_hashes.values())}")


if __name__ == "__main__":
    main()
