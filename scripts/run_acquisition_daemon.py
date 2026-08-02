# -*- coding: utf-8 -*-
"""Launcher for the overnight acquisition daemon — the missing wire in autonomous web learning.

Every part of this loop was already built and none of it ran, because nothing constructed the
daemon. `AcquisitionDaemon` had zero callers outside its own package and its tests (measured
2026-07-28), so gap-detect -> acquire -> consensus -> operator queue existed end to end and was
never once started.

What runs here, and what cannot:
  * intrinsic curiosity supplies the targets — structural holes the SHIPPED graph itself induces,
    so the daemon wants what it is actually missing rather than what someone typed into a list;
  * evidence is live SearXNG + a bounded page fetch (`WebEvidence`), and every claim still passes
    the targeted extractor and the >=2-distinct-domain consensus gate before it counts;
  * writes go to a scratch COPY of the graph plus the queue and ledger files. The daemon refuses
    at construction to let scratch_root equal shipped_root, and promotion out of the queue stays
    operator-signed. Nothing here can change what ATANOR answers with.

Live web is opt-in: with no --live the run reports the targets curiosity found and stops, so the
daemon can be inspected before it is allowed to fetch anything.

  python scripts/run_acquisition_daemon.py                 # show what it would pursue
  python scripts/run_acquisition_daemon.py --live --cycles 3
"""
from __future__ import annotations

import argparse
import dataclasses
import time
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:                              # repo-root imports, as the other scripts do
    sys.path.insert(0, str(REPO))

from packages.acquisition_daemon import AcquisitionQueue, GapLedger
from packages.acquisition_daemon.daemon import AcquisitionDaemon
from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
from packages.knowledge_acquisition.evidence import (FixtureEvidence, LocalIndexEvidence,
                                                    WebEvidence)

DEFAULT_STATE = Path("data/acquisition_daemon")
TABLE_DIR = Path("data/atanor_index/property_table")


def _open_table():
    """The property table, or None with a printed reason. A missing table must degrade to the mined
    path rather than crash a run that was going to work without it."""
    try:
        from packages.atanor_index.property_table import PropertyTable
        t = PropertyTable(TABLE_DIR)
        print(f"property table: {len(t):,} keys over {t.corpora}", flush=True)
        return t
    except Exception as exc:
        print(f"property table unavailable ({exc}) -- running on mined evidence only", flush=True)
        return None


def _run_questions(daemon, args) -> int:
    """Observe a question file in batches, pursuing whatever genuinely abstains. Unattended-safe.

    THE OBSERVE STEP IS THE HONEST PART and it is why a big question file is not a big claim. Each
    question is put to the real graph, and only an actual ``honest_abstain_relational`` becomes
    pressure -- a question ATANOR can already answer records nothing and is never fetched. So the file
    is a CANDIDATE list of holes; the graph decides which are holes.

    A run stops on its own when the file is exhausted, and stops early if a STOP file appears beside
    the state, so the owner can halt an overnight run without finding the process."""
    stop = args.state / "STOP"
    progress = args.state / "progress.json"
    lines = [ln.strip() for ln in args.questions.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    print(f"{len(lines):,} candidate questions from {args.questions}", flush=True)
    print(f"evidence={'CASCADE table->local->web' if args.cascade else 'local corpora' if args.local else 'live web' if args.live else 'none'}  "
          f"curiosity_scan={not args.no_curiosity}  "
          f"observe_rounds={args.observe_rounds}  batch={args.batch}", flush=True)
    print(f"stop by creating {stop}", flush=True)
    print(f"{'asked':>9}{'real gaps':>11}{'pursued':>9}{'queued':>8}"
          f"{'no consensus':>14}{'elapsed':>9}", flush=True)

    totals = {"asked": 0, "gaps": 0, "pursued": 0, "queued": 0, "no_consensus": 0}
    by_tier: dict = {}          # settled_by -> count, and how often each tier was consulted at all
    consulted: dict = {}
    started = time.time()
    for i in range(0, len(lines), args.batch):
        if stop.exists():
            print("STOP file present -- halting", flush=True)
            break
        batch = lines[i:i + args.batch]
        recorded = 0
        for _round in range(max(1, args.observe_rounds)):
            recorded = daemon.observe(batch, source="deficit_map")
        totals["asked"] += len(batch)
        totals["gaps"] += recorded
        rep = dataclasses.asdict(daemon.tick(cycle=i // args.batch))
        totals["pursued"] += int(rep.get("pursued", 0))
        totals["queued"] += int(rep.get("verified_queued", 0))
        totals["no_consensus"] += int(rep.get("insufficient_consensus", 0))
        for e in rep.get("detail") or []:
            for tname in (e.get("tiers_run") or []):
                consulted[tname] = consulted.get(tname, 0) + 1
            if e.get("settled_by"):
                by_tier[e["settled_by"]] = by_tier.get(e["settled_by"], 0) + 1
        el = time.time() - started
        print(f"{totals['asked']:>9,}{totals['gaps']:>11,}{totals['pursued']:>9,}"
              f"{totals['queued']:>8,}{totals['no_consensus']:>14,}{el / 3600:>8.2f}h", flush=True)
        progress.write_text(json.dumps({**totals, "elapsed_h": el / 3600,
                                        "questions_total": len(lines),
                                        "live": bool(args.live), "pause_s": args.pause,
                                        "settled_by_tier": by_tier, "tier_consulted": consulted,
                                        "tier": "operator_queue", "promoted": 0}, indent=2),
                            encoding="utf-8")
        if args.pause and i + args.batch < len(lines):
            time.sleep(args.pause)
    if consulted:
        print(f"tier consulted: {consulted}", flush=True)
        print(f"settled by:     {by_tier}", flush=True)
    print(json.dumps({"mode": "questions", **totals,
                      "settled_by_tier": by_tier, "tier_consulted": consulted,
                      "note": "queued items are PROPOSALS; promotion stays operator-signed"},
                     ensure_ascii=False, indent=1), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="fetch real evidence from SearXNG; without it nothing is fetched")
    ap.add_argument("--cascade", action="store_true",
                    help="table -> local corpora -> web, each tier consulted only while the floor "
                         "is unmet. The tiers differ by three orders of magnitude in cost and the "
                         "expensive one has a hard external limit: continuous querying suspended "
                         "every upstream search engine inside an hour on 2026-07-31. A cheap tier "
                         "that settles the question means the costly one is never asked. Ordering "
                         "evidence by cost cannot change what counts as evidence -- every tier adds "
                         "to the same tally under the same floor.")
    ap.add_argument("--table", action="store_true",
                    help="also feed the precomputed property table into the consensus tally. Same "
                         "floor, same rule: the tally counts distinct DOMAINS, so a fact the table "
                         "read out of Wikipedia and a fact fetched from a Wikipedia page collapse "
                         "to one source instead of reaching the floor between them.")
    ap.add_argument("--local", action="store_true",
                    help="take evidence from ATANOR OWN corpora instead of the network. No search "
                         "provider, so no rate limit -- which is the ceiling that stopped the first "
                         "overnight run. Needs at least two corpora built, or the two-domain "
                         "consensus gate can never be satisfied.")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--shipped", type=Path, default=Path(SHIPPED_GRAPH_ROOT))
    ap.add_argument("--min-pressure", type=int, default=1)
    ap.add_argument("--max-targets", type=int, default=10,
                    help="how many curiosity targets to show in the no-fetch report")
    ap.add_argument("--max-holes", type=int, default=None,
                    help="how many structural holes curiosity may hold at once. StructuralGapScanner "
                         "defaults to 64, which bounds a whole RUN: the holes are scanned once and "
                         "cached, and `tick` refuses to re-pursue a handled gap_key, so extra cycles "
                         "past the 64th target are no-ops. An unattended overnight run needs this "
                         "raised or it finishes in minutes and looks like it worked.")
    ap.add_argument("--max-holes-per-relation", type=int, default=None,
                    help="cap per relation (default 32), so one prolific relation cannot fill the "
                         "whole budget and starve the rest")
    ap.add_argument("--no-curiosity", action="store_true",
                    help="skip the structural-hole scan. It runs bincount and argsort across the "
                         "115M-row columns, which measured 6.5 GB and climbing on a machine with "
                         "1.8 GB free -- enough to take an unrelated overnight job down with it. "
                         "Disabled means the daemon runs on OBSERVED abstentions only.")
    ap.add_argument("--questions", type=Path, default=None,
                    help="a file of questions, one per line, to observe as the endogenous source "
                         "instead of the structural scan. Each is asked against the real graph and "
                         "only a genuine honest_abstain_relational is recorded, so a question that "
                         "is already answerable contributes nothing.")
    ap.add_argument("--observe-rounds", type=int, default=2,
                    help="how many times each question is observed. MIN_PRESSURE is 2 and the "
                         "doctrine is that a one-off abstention is remembered but not pursued, so "
                         "the default reaches the floor honestly rather than lowering it.")
    ap.add_argument("--batch", type=int, default=150,
                    help="questions observed per tick, so progress and the ledger are flushed often")
    ap.add_argument("--pause", type=float, default=0.0,
                    help="seconds to wait between batches. NOT a politeness gesture -- a measured "
                         "necessity. About an hour of continuous querying got SearXNG's upstreams to "
                         "suspend it (google CAPTCHA, brave too-many-requests, duckduckgo and mojeek "
                         "and qwant access-denied) and results collapsed 33 -> 10 -> 0. An unattended "
                         "run at full speed learns nothing after the first hour and spends the whole "
                         "night hammering services that have already said no.")
    args = ap.parse_args()

    state = args.state
    state.mkdir(parents=True, exist_ok=True)
    daemon = AcquisitionDaemon(
        shipped_root=args.shipped,
        scratch_root=state / "scratch",                    # never the shipped store
        evidence=([("local", LocalIndexEvidence()), ("web", WebEvidence())] if args.cascade
                  else LocalIndexEvidence() if args.local
                  else WebEvidence() if args.live else FixtureEvidence({})),
        queue=AcquisitionQueue(state / "queue.jsonl"),
        ledger=GapLedger(state / "ledger.json"),
        min_pressure=args.min_pressure,
        enable_curiosity=not args.no_curiosity,
        property_table=_open_table() if (args.table or args.cascade) else None,
        curiosity_kwargs={k: v for k, v in
                          (("max_holes", args.max_holes),
                           ("max_holes_per_relation", args.max_holes_per_relation))
                          if v is not None},
        log=lambda *a, **k: print(*a, flush=True),
    )

    if args.questions:
        return _run_questions(daemon, args)

    targets = daemon.curiosity_targets()
    if not args.live:
        print(json.dumps({
            "mode": "inspect (no evidence fetched)",
            "shipped_root": str(args.shipped),
            "curiosity_targets_found": len(targets),
            "sample": [t.get("question") or t.get("gap_key") for t in targets[:args.max_targets]],
            "next": "re-run with --live to let it gather evidence for these",
        }, ensure_ascii=False, indent=1))
        return 0

    reports = [daemon.tick(cycle=i).as_dict() for i in range(max(1, args.cycles))]
    print(json.dumps({"mode": "live", "curiosity_targets_found": len(targets),
                      "cycles": reports}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
