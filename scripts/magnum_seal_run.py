# -*- coding: utf-8 -*-
"""Magnum Tier A FORMAL SEAL — the run that upgrades 'provisional 6/6' to sealed.

Protocol (the debt named in the AGI map, P3): every harness A1-A6 at FULL N, under a NETWORK CUT,
executed TWICE — a sealed verdict is a reproduced verdict. The network cut is enforced per-child
via environment: every proxy variable points at a dead local port and the SearXNG address is
poisoned, so any code path that tries the web fails fast instead of quietly phoning out. Each
harness runs in its own interpreter (no shared caches between runs; run 2 cannot inherit run 1).

Output: data/magnum_opus/seal_run.json — per-harness verdicts for both runs + reproduction check.
Honest scope: 'sealed' here claims exactly what was run — full N, no network, twice, same verdict.

  python scripts/magnum_seal_run.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "magnum_opus" / "seal_run.json"

HARNESSES = [
    ("A1", ["scripts/magnum_a1_live_learning.py", "500", "100"]),
    ("A2", ["scripts/magnum_a2_personal_context.py"]),
    ("A3", ["scripts/magnum_a3_honesty_stress.py"]),
    ("A4", ["scripts/magnum_a4_immunity.py"]),
    ("A5", ["scripts/magnum_a5_footprint.py"]),
    ("A6", ["scripts/magnum_a6_continuity.py"]),
]

_VERDICT = re.compile(r"\b(A\d)\s+(PASS|FAIL|[A-Z_]+)\b")


def _cut_env() -> dict[str, str]:
    """Cut the EXTERNAL web, keep LOCALHOST. ATANOR is a local AI — the seal proves it answers from
    its own store with no outside help, so the local engine (127.0.0.1:8502) must stay reachable;
    only the external world (SearXNG, the open web, advisor CLIs) is severed. The first attempt
    poisoned localhost too, which wedged every engine-HTTP harness for the full timeout."""
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        env[k] = "http://127.0.0.1:9"          # discard port — external hosts refuse instantly
    env["NO_PROXY"] = "localhost,127.0.0.1,::1"  # the local engine bypasses the cut; the web does not
    env["no_proxy"] = "localhost,127.0.0.1,::1"
    env["ATANOR_SEARX"] = "http://127.0.0.1:9"  # poisoned search endpoint (external web learning)
    env["ATANOR_OFFLINE"] = "1"                  # any module that honors it stops reaching out
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# Bootstrap: set a hard socket timeout BEFORE the harness imports anything, so an accidental web
# call under the network cut fails in seconds instead of hanging on a connect timeout (the first
# seal run wedged for 115 min this way). Then run the real script with its argv intact.
_BOOT = (
    "import socket,sys,runpy;socket.setdefaulttimeout(8);"
    "sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')"
)
PER_HARNESS_TIMEOUT = int(os.getenv("SEAL_TIMEOUT", "150"))   # env-overridable for a patient re-run

# In-process harnesses are self-contained: the network cut is real and enforceable from here.
# Engine-HTTP harnesses (A2-A6) drive the live :8502 server, which owns its OWN network — a true
# cut needs the ENGINE restarted offline (flagged remaining debt), so their verdict here reflects
# the LIVE engine, and 'cut_enforceable' says so honestly rather than pretending.
IN_PROCESS = {"A1"}


def _run_once(tag: str, argv: list[str], env: dict[str, str]) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-c", _BOOT, *argv], cwd=str(REPO), env=env,
                           capture_output=True, text=True, timeout=PER_HARNESS_TIMEOUT,
                           encoding="utf-8", errors="replace")
        tail = (p.stdout or "").strip().splitlines()[-3:]
        m = _VERDICT.search("\n".join(tail))
        verdict = m.group(2) if m else ("PASS" if p.returncode == 0 else "ERROR")
        return {"harness": tag, "verdict": verdict, "rc": p.returncode, "tail": tail,
                "cut_enforceable": tag in IN_PROCESS, "elapsed_s": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"harness": tag, "verdict": "TIMEOUT", "rc": -1, "tail": [],
                "cut_enforceable": tag in IN_PROCESS, "elapsed_s": round(time.time() - t0, 1)}


def main() -> int:
    env = _cut_env()
    report = {"protocol": "full-N + network-cut + 2x reproduction",
              "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "runs": []}
    for run_i in (1, 2):
        run = []
        for tag, argv in HARNESSES:
            r = _run_once(tag, argv, env)
            run.append(r)
            print(f"run{run_i} {tag}: {r['verdict']} ({r['elapsed_s']}s)")
        report["runs"].append(run)
    # reproduction: a sealed verdict is the SAME verdict twice
    v1 = {r["harness"]: r["verdict"] for r in report["runs"][0]}
    v2 = {r["harness"]: r["verdict"] for r in report["runs"][1]}
    report["reproduced"] = {h: (v1[h] == v2[h]) for h in v1}
    # a SEALED pass claims network-cut only where the cut is actually enforceable (in-process)
    report["sealed_pass"] = sorted(h for h in v1 if v1[h] == "PASS" and v2[h] == "PASS"
                                   and h in IN_PROCESS)
    report["live_engine_pass"] = sorted(h for h in v1 if v1[h] == "PASS" and v2[h] == "PASS"
                                        and h not in IN_PROCESS)
    report["seal_debt"] = ("A2-A6 drive the live :8502 engine, which owns its own network; a true "
                           "cut needs the engine restarted offline. Their verdicts here are "
                           "live-engine, reproduced, but NOT network-sealed.")
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSEALED PASS (both runs, no network): {report['sealed_pass']}")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
