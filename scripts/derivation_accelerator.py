#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the legacy derivation accelerator on an explicit scratch store.

The web learner adds NEW facts slowly and carefully. This is the compounding
lane: is_a / located_in / part_of are transitive (A⊂B ∧ B⊂C ⟹ A⊂C), so a
22M-edge transitive backbone entails tens of millions of edges it hasn't written
down. This script materializes them at ~3/4-million edges/sec — every edge sound
(follows from two stated edges), source-tagged `derived:*`, never fabricated.

    python scripts/derivation_accelerator.py --store <scratch-store> \
        --passes 20 --max-new 1000000

The operator-signed shipped graph is rejected before it is opened or scanned.
The legacy blind closure was measured at roughly 30% wrong on the noisy live
taxonomy, so throughput is a mechanism measurement, not capability progress.
Nothing from this script may be promoted before independent E4/E5 evaluation.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _d in sorted(glob.glob(str(ROOT / "packages" / "*"))):
    if os.path.isdir(_d):
        sys.path.append(_d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--store",
        required=True,
        help="explicit writable scratch store; canonical shipped graph is refused",
    )
    ap.add_argument("--passes", type=int, default=10, help="bounded passes to run")
    ap.add_argument("--max-new", type=int, default=1_000_000, help="edge cap per pass")
    ap.add_argument("--edge-window", type=int, default=1_000_000, help="stated edges scanned per pass")
    ap.add_argument("--sweep", action="store_true", help="run passes until the cursor wraps the whole graph")
    args = ap.parse_args()

    from packages.graph_scale.graph_paths import is_shipped_graph_root
    from packages.graph_scale.derivation_accelerator import accelerate
    from packages.graph_scale.triple_store import TripleStore

    store_root = Path(args.store)
    if is_shipped_graph_root(store_root):
        print(
            "REFUSING before scan: canonical shipped graph is read-only and "
            "derivation has no E4/E5 promotion authority"
        )
        return 2
    store = TripleStore(store_root)

    start_total = len(store)
    cursor = 0
    added = 0
    t0 = time.time()
    p = 0
    while True:
        p += 1
        res = accelerate(store, max_new=args.max_new, edge_window=args.edge_window, cursor=cursor)
        if res.get("error"):
            print(f"pass {p}: ERROR {res['error']}")
            break
        cursor = int(res.get("next_cursor") or 0)
        added += int(res.get("derived") or 0)
        print(f"pass {p:>3}: +{res.get('derived'):>9,} derived  "
              f"({res.get('rate_per_sec'):>8,}/s)  total={len(store):,}  cursor={cursor:,}")
        if args.sweep:
            if res.get("wrapped"):
                break
        elif p >= args.passes:
            break
    dt = time.time() - t0
    print(f"\ndone: +{added:,} new derived connections in {dt:.1f}s "
          f"({round(added / dt):,}/s), store {start_total:,} -> {len(store):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
