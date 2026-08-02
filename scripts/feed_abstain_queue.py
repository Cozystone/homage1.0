#!/usr/bin/env python3
"""Drain the abstain queue (CLI wrapper — logic lives in packages/graph_scale/abstain_feeder
so the continuous-learning daemon can call the same drain()).

  python scripts/feed_abstain_queue.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.graph_scale.abstain_feeder import drain  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    counters = drain(limit=args.limit, dry_run=args.dry_run)
    print(f"done: {counters}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
