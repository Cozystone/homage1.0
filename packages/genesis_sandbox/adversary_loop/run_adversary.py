# -*- coding: utf-8 -*-
"""Run the ATANOR DEFENDER adversary loop and print the six-surface scorecard.

    python -X utf8 -m packages.genesis_sandbox.adversary_loop.run_adversary
    python -X utf8 -m packages.genesis_sandbox.adversary_loop.run_adversary --budget 6 --seed 7

White-hat, isolated, in-process. No external service, no network listener, no production engine.
Exit code 1 iff any surface BREACHED (for CI), else 0.
"""
from __future__ import annotations

import argparse
import sys

from packages.genesis_sandbox.adversary_loop.loop import AdversaryLoop, LoopConfig, LoopReport
from packages.genesis_sandbox.adversary_loop.scoring import BREACH, GAP, HOLD, NA, worst_severity
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget

_ORDER = ["a", "b", "c", "d", "e", "f"]


def _verdict_mark(v: str) -> str:
    return {HOLD: "HOLD  ", BREACH: "BREACH", NA: "N/A   "}.get(v, v)


def print_report(report: LoopReport) -> None:
    print("=" * 82)
    print("ATANOR DEFENDER -- SIX-SURFACE SECURITY SCORECARD (white-hat, isolated, in-process)")
    print("=" * 82)
    print(f"{'SURFACE':<40}{'VERDICT':<8}{'COUNTS':<28}{'WORST'}")
    print("-" * 82)
    for key in _ORDER:
        s = report.surfaces.get(key)
        if s is None:
            continue
        c = s.counts()
        counts = f"HOLD={c[HOLD]} BREACH={c[BREACH]} GAP={c[GAP]} N/A={c[NA]}"
        worst = worst_severity(s.results) or "-"
        print(f"{key + ') ' + s.surface_name:<40}{_verdict_mark(s.verdict):<8}{counts:<28}{worst}")
    print("-" * 82)
    print(f"ledger: {report.recorded_breaches} breach(es) + {report.recorded_gaps} gap(s) recorded; "
          f"{report.proposals} staged hardening proposal(s)")
    print("=" * 82)

    # per-surface detail: every BREACH (full repro) + a sample of GAPs.
    for key in _ORDER:
        s = report.surfaces.get(key)
        if s is None:
            continue
        breaches = s.breaches()
        gaps = s.gaps()
        nas = [r for r in s.results if r.outcome == NA]
        print(f"\n[{key}] {s.surface_name}  ->  {s.verdict}")
        if nas:
            print(f"   N/A: {nas[0].detail}")
        for r in breaches:
            print(f"   BREACH [{r.severity}] via {r.technique}")
            print(f"      input:    {r.attack_input[:110]}")
            print(f"      observed: {r.observed}")
            print(f"      -> {r.detail}")
        for r in gaps[:3]:
            print(f"   GAP [{r.severity}] via {r.technique}")
            print(f"      input:    {r.attack_input[:110]}")
            print(f"      -> {r.detail}")
            if r.backstop:
                print(f"      backstop: {r.backstop}")
        if len(gaps) > 3:
            print(f"   ... +{len(gaps) - 3} more GAP(s) recorded in the ledger")
        if not breaches and not gaps and not nas:
            print("   all trials HELD.")

    print("\n" + "=" * 82)
    if report.any_breach():
        print("RESULT: BREACH DETECTED -- at least one surface failed. See detail above + the ledger.")
    else:
        print("RESULT: NO BREACH -- every reachable surface held. GAPs are documented heuristic limits,")
        print("        each backstopped by an outer layer; N/A surfaces were NOT scored as holding.")
    print("=" * 82)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ATANOR DEFENDER adversary loop (Step 1, local).")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--budget", type=int, default=10, help="mutation trials per held seed")
    ap.add_argument("--no-membrane", action="store_true", help="probe surface (a) with the conformal gate OFF")
    args = ap.parse_args(argv)

    target = IsolatedTarget(membrane_live=not args.no_membrane)
    loop = AdversaryLoop(target, config=LoopConfig(seed=args.seed, budget_per_seed=args.budget))
    report = loop.run()
    print_report(report)
    print(f"\nartifacts under: {target.sandbox_dir}")
    return 1 if report.any_breach() else 0


if __name__ == "__main__":
    sys.exit(main())
