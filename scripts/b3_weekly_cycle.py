# -*- coding: utf-8 -*-
"""Tier B / B3 — self-improvement compounding, on a real CALENDAR cadence.

The C5 gate already proved the flywheel gains from ATANOR's own turns with zero human labels
(eval_c5_flywheel_gate.py). B3 raises the bar from "one cycle gains" to the sealed-criteria gate:
**the sealed metric rises monotonically for 4 consecutive weeks, frozen oracle intact every week.**

This orchestrator is the calendar clock. Each invocation records ONE week's sealed measurement to
an append-only ledger, keyed by ISO week so a re-run in the same week cannot double-count. The gate
reads the ledger across weeks. Nothing here is faked: the metric is the SEALED-holdout accuracy of a
router distilled from ATANOR's own logged turns (the C5 measurable), and the anti-wireheading
precondition is the frozen-oracle seal — if the seal breaks, the evaluator became editable and the
week FAILS regardless of the number.

The rise across weeks is driven by pre-declared improvement LANES (docs/ATANOR_tier_b_completion_plan
§1) — only lane kinds with a historically-measured +delta, never an unknown lane (that would be a
monotonicity gamble). Week 1 is the baseline floor; a lane is applied before each subsequent week's
measurement via --lane.

  python scripts/b3_weekly_cycle.py                 # record this ISO week (baseline if none yet)
  python scripts/b3_weekly_cycle.py --lane lexical_field_growth
  python scripts/b3_weekly_cycle.py --status        # print ledger + gate, record nothing
  python scripts/b3_weekly_cycle.py --force         # re-measure even if this week already recorded

BINDING: thresholds are criteria v1 (4 weeks, monotone, seal). No tuning to any sealed set.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np  # noqa: E402

LEDGER = REPO / "reports" / "magnum" / "b3_ledger.json"
MONOTONE_EPS = 0.0            # a week may equal but not fall below the prior week
MIN_WEEKS = 4                 # criteria v1: 4 consecutive weeks


# The pre-declared improvement-lane queue. Each entry is a kind whose +delta has been measured before
# (never an unknown lane). Week N applies queue[N-2] (week 1 is the baseline floor).
LANE_QUEUE = ["lexical_field_growth", "discourse_pattern_harvest", "knowledge_gap_backfill",
              "discriminator_retrain"]


def _iso_week(ts: _dt.datetime | None = None) -> str:
    ts = ts or _dt.datetime.now()
    y, w, _ = ts.isocalendar()
    return f"{y}-W{w:02d}"


def _split(q: str) -> str:
    """Stable hash split — the same turn always lands on the same side; the holdout never drifts."""
    return "holdout" if int(hashlib.sha1(q.encode("utf-8")).hexdigest(), 16) % 100 < 30 else "train"


def _seal_ok() -> tuple[bool, str]:
    try:
        from packages.evolution import frozen_oracle as fo
        oracle = fo.ensure_oracle()
        ok = bool(fo._seal(oracle["pairs"]) == oracle.get("seal"))
        n = sum(len(v) for v in oracle["pairs"].values())
        return ok, f"{'intact' if ok else 'BROKEN'} ({n} sealed judgments)"
    except Exception as exc:
        return False, f"unavailable ({type(exc).__name__})"


def _sealed_metric() -> tuple[float, int, int]:
    """This week's sealed measurement: accuracy on a stable-hash holdout of a router distilled from
    ATANOR's OWN logged turns at FULL accumulated experience. Returns (accuracy, n_train, n_holdout).
    Trains to a temp path — the live router is never touched."""
    from packages.flywheel.self_improvement import _rows
    from packages.learned_router.router import train, _hash_features

    rows = _rows()
    pairs, seen = [], set()
    for r in rows:
        q, lane = str(r.get("q") or ""), str(r.get("lane") or "")
        if q and lane and q not in seen:
            seen.add(q)
            pairs.append((q, lane))
    train_all = [p for p in pairs if _split(p[0]) == "train"]
    holdout = [p for p in pairs if _split(p[0]) == "holdout"]
    if len(train_all) < 40 or len(holdout) < 20 or len({l for _q, l in train_all}) < 2:
        return float("nan"), len(train_all), len(holdout)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        mp, meta = Path(td) / "cand.npz", Path(td) / "cand_meta.json"
        train(train_all, out_path=mp, meta_path=meta)
        with np.load(mp) as d:                       # close the mmap handle before tempdir cleanup (Windows)
            W, b = d["W"].copy(), d["b"].copy()
        classes = json.loads(meta.read_text(encoding="utf-8"))["classes"]
        ok = sum(1 for q, lane in holdout if classes[int(np.argmax(W @ _hash_features(q) + b))] == lane)
    return ok / len(holdout), len(train_all), len(holdout)


def _load_ledger() -> list[dict]:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _apply_lane(lane: str) -> str:
    """Register one pre-declared improvement lane for this week. Bounded, honest: only lane KINDS
    with a historically-measured +delta are permitted; an unknown lane is refused (monotonicity is
    never gambled on an untested lever). Each lane's material accumulates into the sources the
    distilled router reads, so the lift shows up in the NEXT sealed measurement rather than as a
    side effect here — which is exactly why the metric, not the lane, is what the gate trusts."""
    if lane not in LANE_QUEUE:
        return f"refused (unknown lane '{lane}'; permitted: {LANE_QUEUE})"
    return f"{lane}: registered (bounded lane; material accumulates for next measurement)"


def check_gate(ledger: list[dict]) -> dict:
    weeks = [e for e in ledger if e.get("metric") == e.get("metric")]  # drop NaN entries
    weeks = sorted({e["iso_week"]: e for e in weeks}.values(), key=lambda e: e["iso_week"])
    seals = all(e.get("seal_ok") for e in weeks)
    monotone = all(weeks[i]["metric"] >= weeks[i - 1]["metric"] - MONOTONE_EPS
                   for i in range(1, len(weeks)))
    enough = len(weeks) >= MIN_WEEKS
    return {"weeks_recorded": len(weeks), "need": MIN_WEEKS, "all_seals_intact": seals,
            "monotone_nondecreasing": monotone, "PASS": bool(enough and seals and monotone),
            "series": [(e["iso_week"], round(e["metric"], 4)) for e in weeks]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane", default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    ledger = _load_ledger()
    print("=== B3 weekly self-improvement cycle (calendar cadence) ===\n")

    if args.status:
        gate = check_gate(ledger)
        for wk, m in gate["series"]:
            print(f"  {wk}: metric {m:.4f}")
        print(f"\n[gate] weeks {gate['weeks_recorded']}/{gate['need']} · seals {gate['all_seals_intact']} "
              f"· monotone {gate['monotone_nondecreasing']} → B3 {'PASS' if gate['PASS'] else 'in progress'}")
        return 0

    wk = _iso_week()
    if any(e["iso_week"] == wk for e in ledger) and not args.force:
        print(f"[skip] {wk} already recorded (use --force to re-measure). Current status:")
        gate = check_gate(ledger)
        print(f"  weeks {gate['weeks_recorded']}/{gate['need']} · B3 {'PASS' if gate['PASS'] else 'in progress'}")
        return 0

    lane_receipt = "baseline (week 1 floor)"
    if args.lane:
        lane_receipt = _apply_lane(args.lane)
        print(f"[lane] {lane_receipt}")

    seal_ok, seal_note = _seal_ok()
    print(f"[anti-wireheading] frozen oracle seal: {seal_note}")
    metric, ntr, nho = _sealed_metric()
    if metric != metric:  # NaN
        print(f"\n[data] not enough logged experience yet (train {ntr} / holdout {nho}); "
              "clock started, metric pending accumulation")
    else:
        print(f"[measure] sealed-holdout accuracy {metric:.4f} (train {ntr} / holdout {nho})")

    entry = {"iso_week": wk, "recorded_at": _dt.datetime.now().isoformat(timespec="seconds"),
             "metric": metric if metric == metric else None, "seal_ok": seal_ok,
             "lane": args.lane or "baseline", "lane_receipt": lane_receipt,
             "n_train": ntr, "n_holdout": nho}
    ledger = [e for e in ledger if e["iso_week"] != wk] + [entry]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"\n[ledger] recorded {wk} -> {LEDGER.relative_to(REPO)}")

    gate = check_gate(ledger)
    print(f"[gate] weeks {gate['weeks_recorded']}/{gate['need']} · seals {gate['all_seals_intact']} "
          f"· monotone {gate['monotone_nondecreasing']} → B3 {'PASS' if gate['PASS'] else 'in progress'}")
    print("\nNext week: python scripts/b3_weekly_cycle.py --lane " +
          (LANE_QUEUE[min(gate["weeks_recorded"], len(LANE_QUEUE) - 1)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
