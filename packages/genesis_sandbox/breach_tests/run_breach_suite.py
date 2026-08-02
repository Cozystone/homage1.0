# -*- coding: utf-8 -*-
"""Run the full red-team breach suite and print a per-layer HOLD/BREACH table.

    python -X utf8 -m packages.genesis_sandbox.breach_tests.run_breach_suite

Every trial runs CONTAINED against OUR OWN layers (in-process or the sandbox's own restricted
subprocess). No external host is contacted, no real data exfiltrated, no real harm attempted,
and L0 is never actually disabled (the trials verify it refuses / fails closed).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from packages.genesis_sandbox.breach_tests import (
    breach_l0_moral, breach_l1_liberation, breach_l2_fs_jail, breach_l3_net,
    breach_l4_resources, breach_l5_process, breach_l6_killswitch,
)
from packages.genesis_sandbox.breach_tests._harness import BREACH, GAP, HOLD, NA, TrialResult, layer_verdict

_LAYERS = [
    ("L0 moral 0th gate (inviolable)", breach_l0_moral),
    ("L1 output-liberation zone", breach_l1_liberation),
    ("L2 filesystem jail", breach_l2_fs_jail),
    ("L3 network isolation", breach_l3_net),
    ("L4 resource limits", breach_l4_resources),
    ("L5 process isolation", breach_l5_process),
    ("L6 kill-switch + audit", breach_l6_killswitch),
]


def run_all(root: Path | None = None) -> dict:
    root = Path(root) if root else Path(tempfile.mkdtemp(prefix="genesis_breach_"))
    root.mkdir(parents=True, exist_ok=True)
    per_layer: dict[str, list[TrialResult]] = {}
    for name, module in _LAYERS:
        per_layer[name] = module.run(root)
    any_breach = any(r.breached for rs in per_layer.values() for r in rs)
    return {"root": str(root), "per_layer": per_layer, "any_breach": any_breach}


def _fmt_counts(results: list[TrialResult]) -> str:
    c = {HOLD: 0, BREACH: 0, GAP: 0, NA: 0}
    for r in results:
        c[r.outcome] = c.get(r.outcome, 0) + 1
    return f"HOLD={c[HOLD]} BREACH={c[BREACH]} GAP={c[GAP]} N/A={c[NA]}"


def print_report(result: dict) -> None:
    per_layer = result["per_layer"]
    print("=" * 78)
    print("GENESIS SANDBOX -- RED-TEAM BREACH REPORT (contained; our own layers only)")
    print("root:", result["root"])
    print("=" * 78)
    header = f"{'LAYER':<34}{'VERDICT':<9}{'COUNTS'}"
    print(header)
    print("-" * 78)
    for name, results in per_layer.items():
        verdict = layer_verdict(results)
        mark = "HOLD " if verdict == HOLD else "BREACH"
        print(f"{name:<34}{mark:<9}{_fmt_counts(results)}")
    print("-" * 78)
    print("\nPER-TRIAL DETAIL:")
    for name, results in per_layer.items():
        print(f"\n[{name}]")
        for r in results:
            print(f"  {r.outcome:<7} {r.trial}")
            print(f"          -> {r.detail}")
    print("\n" + "=" * 78)
    if result["any_breach"]:
        print("RESULT: BREACH DETECTED -- at least one layer failed. See table above.")
    else:
        gaps = sum(1 for rs in per_layer.values() for r in rs if r.outcome == GAP)
        nas = sum(1 for rs in per_layer.values() for r in rs if r.outcome == NA)
        print(f"RESULT: NO BREACH -- all layers held. (honest notes: {gaps} GAP, {nas} N/A)")
    print("=" * 78)


def main() -> int:
    result = run_all()
    print_report(result)
    return 1 if result["any_breach"] else 0


if __name__ == "__main__":
    sys.exit(main())
