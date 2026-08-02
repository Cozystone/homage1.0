# -*- coding: utf-8 -*-
"""Generate honest (proxy, gate) observations -- ONE PER CUE, because recall never sees the relation.

    python scripts/calibrate_proxy.py --want 6

The first attempt at this produced six rows, r=1.0, and two actual data points: the same cue proposed
for four relations gives four identical recall deltas, since the harness measures what the REGEX
extracts and the relation label changes nothing it can see. So candidates are deduplicated BY CUE here,
and `cheap_proxy.calibration` independently discards duplicate observations -- one guard at the source
and one at the reader, because this class of defect has survived a single guard five times today.
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

PE = pathlib.Path("packages/graph_scale/property_extraction.py")
ANCHOR = '    ("made_of", re.compile('


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--want", type=int, default=6)
    ap.add_argument("--top-cues", type=int, default=60)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from packages.meta_diagnosis.cheap_proxy import calibrate_one, calibration
    from packages.self_repair.pattern_proposer import _sample_glosses, evaluate, propose

    c = calibration()
    print(f"start: {c['pairs']} distinct pair(s), "
          f"{c.get('duplicates_discarded', 0)} duplicate(s) already discarded, r={c['r']}")

    rows = _sample_glosses()
    seen, cands = set(), []
    for cand in propose(top_cues=args.top_cues):
        e = evaluate(cand, rows)
        if getattr(e, "regex", None) and e.fired >= 2 and e.cue not in seen:
            seen.add(e.cue)
            cands.append(e)
    print(f"distinct CUES available: {len(cands)}")

    def make(e):
        line = "    (%r, re.compile(%r, re.I))," % (e.relation, e.regex) + "\n"

        def apply_fn():
            orig = PE.read_text(encoding="utf-8")
            PE.write_text(orig.replace(ANCHOR, line + ANCHOR, 1), encoding="utf-8")
            return orig

        def revert_fn(orig):
            PE.write_text(orig, encoding="utf-8")

        return apply_fn, revert_fn

    for e in cands:
        if calibration()["pairs"] >= args.want:
            break
        apply_fn, revert_fn = make(e)
        r = calibrate_one(apply_fn, revert_fn, e.cue)
        if r.get("usable"):
            print(f"  {e.cue:<26} proxy {r['proxy']:+.5f}   gate {r['sealed_b2']:+.5f}")

    c = calibration()
    print()
    print(f"DISTINCT pairs {c['pairs']} | duplicates discarded {c.get('duplicates_discarded')} "
          f"| r = {c['r']}")
    print(c["usable_for"])


if __name__ == "__main__":
    main()
