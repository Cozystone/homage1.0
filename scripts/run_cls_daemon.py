# -*- coding: utf-8 -*-
"""Run the CLS organism as a service (or one cycle). Consolidation runs with no web at all; wire a real
harvester to activate curiosity.

  python scripts/run_cls_daemon.py --once            # a single cycle (cron-friendly)
  python scripts/run_cls_daemon.py --interval 3600   # loop hourly (kill-switch: touch live_memory/cls_daemon.stop)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from packages.reasoning_vm.cls_daemon import loop
    once = "--once" in sys.argv
    interval = 3600.0
    if "--interval" in sys.argv:
        interval = float(sys.argv[sys.argv.index("--interval") + 1])
    harvester = None            # default: consolidation-only (safe). A live searxng/profile harvester is
    #                             wired here at deploy to activate autonomous curiosity.
    return loop(interval_s=interval, harvester=harvester, once=once)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
