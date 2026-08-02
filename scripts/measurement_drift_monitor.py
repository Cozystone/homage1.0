#!/usr/bin/env python3
"""Measurement-isolation drift monitor (READ-ONLY) — ATLASky AAIC/CGR-CUSUM slice.

Operationalizes Codex's Q3 consult on the ATLASky-AI adoption: the CUSUM target
must track a QUALITY-rate rolling baseline, NOT store size, so that *healthy
graph growth* is distinguished from *drift you must freeze measurement on*.

It samples a store N times over a short window (the live store may be mutated by
the background learner) and reports:
  * measurement_isolation: did case_frames hash change BETWEEN samples while we
    were measuring? (this is exactly what invalidated the P1 delta today)
  * quality invariants: leak == 0 and negative-fixture predicate_anchor == 0
  * CGR-CUSUM Si on the predicate_anchor quality rate
      Si(t) = max(0, Si(t-1) + (p_i - mu0 - k)),  k=0.05, fire at h=5.0  (per paper)
  * classification: stable | healthy_growth | measurement_isolation_drift |
    quality_regression

NON-DESTRUCTIVE: never writes the store; only reads it and writes a report under
reports/drift-monitor/. Reuses the P0 audit (also read-only) for the metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import derivation_p0_audit as dp0  # noqa: E402

# CGR-CUSUM constants (paper: k=0.05 allowance, h=5.0 fire threshold).
CUSUM_K = 0.05
CUSUM_H = 5.0
# Labels whose predicate_anchor MUST stay 0 (firing here = quality regression).
NEGATIVE_LABELS = ("alias_or_failure_negative", "non_attribution_distractor", "abstain_expected")


def _case_frames_hash(store_dir: Path) -> tuple[str, int]:
    cf = store_dir / "case_frames.jsonl"
    if not cf.exists():
        return ("", 0)
    data = cf.read_bytes()
    return (hashlib.sha256(data).hexdigest()[:16], data.count(b"\n"))


def _sample(fixture: Path, store_dir: Path) -> dict[str, Any]:
    report = dp0.run_audit(fixture, store_dir)
    m = report["metrics"]
    per_label = report["per_label"]
    negative_anchor = sum(per_label.get(lb, {}).get("predicate_anchor", 0) for lb in NEGATIVE_LABELS)
    h, n = _case_frames_hash(store_dir)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "case_frames_sha": h,
        "case_frames_lines": n,
        "predicate_anchor_hit_rate": m["predicate_anchor_hit_rate"],
        "leak": m["derivation_to_answer_leak_count"],
        "negative_anchor": negative_anchor,
    }


def run_monitor(
    fixture: Path,
    store_dir: Path,
    samples: int,
    interval_s: float,
    baseline: float | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for i in range(samples):
        rows.append(_sample(fixture, store_dir))
        if i < samples - 1:
            time.sleep(interval_s)

    # CUSUM target mu0. Codex review: a window mean makes cusum_quality_shift
    # nearly inert (it cannot detect a shift away from the window it is computed
    # over). For real AAIC shift detection, pass an EXTERNAL frozen baseline
    # (e.g. a prior approved measurement); only then does the CUSUM track drift
    # away from that reference rather than self-cancelling.
    quals = [r["predicate_anchor_hit_rate"] for r in rows]
    window_mean = round(sum(quals) / len(quals), 4) if quals else 0.0
    if baseline is not None:
        mu0 = float(baseline)
        baseline_source = "external_frozen_baseline"
    else:
        mu0 = window_mean
        baseline_source = "window_mean (inert for shift detection; pass --baseline for AAIC)"

    # CGR-CUSUM on the quality rate (deviation above baseline).
    s = 0.0
    cusum_series: list[float] = []
    fired = False
    for q in quals:
        s = max(0.0, s + (q - mu0 - CUSUM_K))
        cusum_series.append(round(s, 4))
        if s >= CUSUM_H:
            fired = True

    hashes = {r["case_frames_sha"] for r in rows}
    isolation_broken = len(hashes) > 1            # store changed mid-measurement
    leak_clean = all(r["leak"] == 0 for r in rows)
    negatives_clean = all(r["negative_anchor"] == 0 for r in rows)
    anchor_increased = len(quals) >= 2 and quals[-1] > quals[0]

    if not leak_clean or not negatives_clean:
        classification = "quality_regression"
    elif isolation_broken:
        # store legitimately grew (clean) but NOT frozen -> measurement not isolated
        classification = "measurement_isolation_drift"
    elif fired:
        classification = "cusum_quality_shift"
    else:
        classification = "stable"

    return {
        "monitor_id": "measurement_drift_monitor_v0",
        "report_schema_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "store_dir": str(store_dir),
        "samples": samples,
        "interval_s": interval_s,
        "cusum": {"k": CUSUM_K, "h": CUSUM_H, "mu0_quality_baseline": mu0,
                  "baseline_source": baseline_source, "window_mean": window_mean,
                  "series": cusum_series, "fired": fired},
        "invariants": {"leak_clean": leak_clean, "negatives_clean": negatives_clean,
                       "isolation_broken": isolation_broken, "anchor_increased": anchor_increased,
                       "distinct_case_frame_hashes": len(hashes)},
        "classification": classification,
        "interpretation": {
            "stable": "store frozen + quality clean: measurement is trustworthy.",
            "healthy_growth": "anchor up WITH leak=0 and negatives=0 (growth, but isolate before measuring).",
            "measurement_isolation_drift": "store changed mid-measurement (e.g. background learner) -> freeze before any P1 delta.",
            "quality_regression": "leak>0 or a negative-fixture anchored -> hard stop.",
            "cusum_quality_shift": "CGR-CUSUM crossed h -> sustained quality shift, re-tune.",
        }[classification if classification != "measurement_isolation_drift" or not anchor_increased else "measurement_isolation_drift"],
        "samples_detail": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Measurement-isolation drift monitor (read-only)")
    ap.add_argument("--store", type=Path, default=dp0.DEFAULT_STORE)
    ap.add_argument("--fixture", type=Path, default=dp0.DEFAULT_FIXTURE)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--baseline", type=float, default=None,
                    help="external frozen quality baseline mu0 for AAIC shift detection")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "drift-monitor")
    args = ap.parse_args()

    report = run_monitor(args.fixture, args.store, args.samples, args.interval, baseline=args.baseline)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (args.out_dir / f"{ts}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    inv = report["invariants"]
    print(f"[DRIFT] classification={report['classification']}")
    print(f"[DRIFT] isolation_broken={inv['isolation_broken']} distinct_hashes={inv['distinct_case_frame_hashes']} "
          f"leak_clean={inv['leak_clean']} negatives_clean={inv['negatives_clean']}")
    print(f"[DRIFT] mu0={report['cusum']['mu0_quality_baseline']} cusum_fired={report['cusum']['fired']}")
    print(f"[DRIFT] {report['interpretation']}")
    print(f"[DRIFT] report: {args.out_dir / (ts + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
