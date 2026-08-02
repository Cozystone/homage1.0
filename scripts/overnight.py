# -*- coding: utf-8 -*-
"""The night shift — unattended self-repair cycles, one after another, with a written record.

    python scripts/overnight.py            # until stopped
    python scripts/overnight.py --hours 8

WHAT THIS IS AND IS NOT. `autorun.unattended_cycle()` is a whole repair cycle with nobody in it: it
measures, proposes a change, runs the held-out gate, and KEEPS OR REVERTS on the gate's verdict. One
cycle is a few minutes. This runs them back to back and writes what happened, so a night produces a
series rather than an anecdote.

IT CANNOT TOUCH THE GROUND IT IS SCORED ON. `provisional.FORBIDDEN` covers the scoring paths, the
moral gate, the conformal gate and the cycle ledger itself, so nothing here can improve a number by
editing the thing that computes it. That barrier is the reason this is safe to leave running, and it
is also, in the terms of the strange-loop census, exactly where the loop is deliberately cut.

FAILURES ARE RECORDED, NOT SWALLOWED. A cycle that errors writes its error and the next one starts;
a night of silent exceptions would look identical to a night of quiet success, which is the failure
mode this file exists to avoid. The log is data/self_repair/overnight.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LOG = REPO / "data" / "self_repair" / "overnight.jsonl"


def _write(rec: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=0.0, help="0 = until stopped")
    ap.add_argument("--rest", type=float, default=30.0, help="seconds between cycles")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from packages.self_repair.autorun import unattended_cycle

    started = time.time()
    n = ok = failed = kept = 0
    _write({"event": "night_begins", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid()})
    while True:
        if a.hours and (time.time() - started) > a.hours * 3600:
            break
        n += 1
        t0 = time.time()
        try:
            out = unattended_cycle(quiet=True)
            ok += 1
            kept += int(bool(out.get("kept") or out.get("applied")))
            _write({"cycle": n, "seconds": round(time.time() - t0, 1),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": out})
            print("cycle %d ok in %.0fs" % (n, time.time() - t0), flush=True)
        except Exception as exc:
            failed += 1
            _write({"cycle": n, "seconds": round(time.time() - t0, 1),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "where": traceback.format_exc()[-800:]})
            print("cycle %d FAILED: %s" % (n, type(exc).__name__), flush=True)
        time.sleep(max(1.0, a.rest))
    _write({"event": "night_ends", "cycles": n, "ok": ok, "failed": failed, "kept": kept,
            "hours": round((time.time() - started) / 3600, 2)})
    print(json.dumps({"cycles": n, "ok": ok, "failed": failed, "kept": kept}, indent=1))


if __name__ == "__main__":
    main()
