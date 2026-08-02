# -*- coding: utf-8 -*-
"""B5 final verdict — run all three missions, freeze the artefacts, render the aggregate verdict.

B5 PASS (spec): all three missions' hard gates pass AND full-knowledge mission success >= 85%.
The 3B/8B DOMINATION verdict is WITHHELD by design (no external baseline on this hardware — the
No-LLM doctrine + GPU shared with the live engine; the harness leaves a drop-in baseline slot).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from packages.b5_missions import freeze
from packages.b5_missions import mission_incident, mission_memory, mission_recovery

ROOT = Path(__file__).resolve().parents[2]


def _run(fn) -> tuple[bool, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    out = buf.getvalue()
    passed = "ALL GATES PASS" in out.splitlines()[-2] if out.strip() else False
    return passed, out


def main() -> None:
    manifest = freeze.build_manifest()
    print("=" * 78)
    print("ATANOR B5 real-agent battery -- final verdict")
    print("frozen artefacts (SHA-256):")
    for name, rec in manifest["artifacts"].items():
        tag = rec["sha256"][:16] if rec["sha256"] else "MISSING"
        print(f"  {name:26s} {tag}")
    print("=" * 78)

    results = {}
    for label, fn in [("B5-1 incident", mission_incident.main),
                      ("B5-2 memory", mission_memory.main),
                      ("B5-3 recovery", mission_recovery.main)]:
        ok, out = _run(fn)
        results[label] = ok
        print(out.rstrip())
        print("-" * 78)

    b5_pass = all(results.values())
    print("B5 MISSION SUMMARY")
    for k, v in results.items():
        print(f"  {k:16s} {'PASS' if v else 'FAIL'}")
    print(f"\nB5 VERDICT: {'PASS (all three missions, all hard gates)' if b5_pass else 'FAIL'}")
    print("3B/8B domination verdict: WITHHELD (no external baseline on this hardware -- No-LLM "
          "doctrine + shared GPU; drop-in slot left in harness).")
    print("native blind fluency Likert: DEFERRED (blind human panel, B6-style).")

    out = ROOT / "data" / "b5_missions" / "b5_final_verdict.json"
    out.write_text(json.dumps({"missions": results, "b5_pass": b5_pass,
                               "domination_verdict": "WITHHELD_NO_BASELINE",
                               "fluency_likert": "DEFERRED_HUMAN_PANEL",
                               "frozen": {k: v["sha256"] for k, v in manifest["artifacts"].items()}},
                              indent=2), encoding="utf-8")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
