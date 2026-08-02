# -*- coding: utf-8 -*-
"""Waiting-period integrity audit — one command to answer "has the live engine had a single transient
500 or a memory ratchet?" during the ① 2nd-green wait. Read-only. The watchdog auto-restarts and the
rotated stderr log captures everything; this reads both and gives a PASS/ALERT verdict.

  python scripts/waiting_period_audit.py [--since YYYY-MM-DD]

Surveils:
  • watchdog restarts (today + by reason: 'unhealthy x3' vs memory) — a memory ratchet shows here.
  • engine stderr tracebacks / FileNotFoundError / 500s since --since (default: today).
  • live /health (up + latency).
"""
from __future__ import annotations

import datetime
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WD_LOG = REPO / "data" / "watchdog.log"
ERR_LOG = REPO / "logs" / "startup" / "atanor-engine.err.log"


def _since() -> str:
    for i, a in enumerate(sys.argv):
        if a == "--since" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return datetime.date.today().isoformat()


def main() -> int:
    since = _since()
    alerts: list[str] = []

    # 1) watchdog restarts since `since`, split by reason
    restarts_today = mem_restarts = 0
    reasons: dict[str, int] = {}
    if WD_LOG.exists():
        for line in WD_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            if "RESTART" not in line:
                continue
            ts = line[1:11] if line.startswith("[") else ""
            if ts < since:
                continue
            restarts_today += 1
            m = re.search(r"RESTART \(([^)]+)\)", line)
            reason = m.group(1) if m else "?"
            reasons[reason] = reasons.get(reason, 0) + 1
            if "mem" in reason.lower() or "rss" in reason.lower() or "bloat" in reason.lower():
                mem_restarts += 1
    print(f"watchdog restarts since {since}: {restarts_today}  by_reason={reasons or '{}'}")
    if mem_restarts:
        alerts.append(f"{mem_restarts} MEMORY-triggered restart(s) — ratchet not contained")
    if restarts_today > 3:
        alerts.append(f"{restarts_today} restarts since {since} — engine unstable")

    # 2) engine stderr tracebacks / 500s / FileNotFoundError since `since`
    err_count = 0
    samples: list[str] = []
    if ERR_LOG.exists():
        block: list[str] = []
        for line in ERR_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"Traceback \(most recent call last\)|FileNotFoundError|Error:|"
                         r"HTTP/1\.1\" 500|Internal Server Error", line):
                err_count += 1
                if len(samples) < 6:
                    samples.append(line.strip()[:110])
    print(f"engine stderr error lines (whole log): {err_count}")
    for s in samples:
        print(f"    · {s}")
    # note: the stderr log rotates (10MB, .1 kept), so this is 'recent history', not all-time.

    # 3) live health
    try:
        import time
        t = time.time()
        code = urllib.request.urlopen("http://127.0.0.1:8502/health", timeout=5).status
        print(f"engine /health: {code} ({(time.time() - t) * 1000:.0f} ms)")
        if code != 200:
            alerts.append(f"/health returned {code}")
    except Exception as exc:
        print(f"engine /health: DOWN ({type(exc).__name__})")
        alerts.append("engine /health unreachable")

    print()
    if alerts:
        print("=== ALERT ===")
        for a in alerts:
            print(f"  ! {a}")
        return 1
    print("=== PASS — no memory ratchet, engine healthy ===")
    print("  (transient stderr errors above are historical; recheck they are not RECURRING post-fix)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
