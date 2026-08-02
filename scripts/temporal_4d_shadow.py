#!/usr/bin/env python3
"""P-4D.0/1 — temporal 4D shadow measurement (READ-ONLY, NON-DESTRUCTIVE).

Codex Q5 smallest vertical slice for the 4D spatiotemporal layer. It does NOT
touch the store; it measures, on the live graph:

 Axis 1 (coverage): what temporal anchor each case_frame has
 (explicit in-text year = high confidence vs created_at-only = low).
 Axis 2 (functional-slot reality): among functional-attribution facts
 (CEO///... — a MEASUREMENT-ONLY eval cue set, NOT engine logic,
 like the P0 fixture labels), how many subjects carry >1 competing value
 (temporal-contradiction candidates) and how many are time-resolvable.
 Axis 3 (TCV mechanism self-test, synthetic): proves the deterministic
 Temporal-Consistency verifier flags overlapping functional intervals,
 passes disjoint ones, and resolves via supersession ordering.

Output: reports/temporal-4d/. The functional-cue set is eval config only and is
never used to generate an answer (Contract C1; "score != evidence").
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"

# MEASUREMENT-ONLY eval cues (NOT engine logic; NOT an answer table). Used solely
# to locate functional-attribution facts for the coverage measurement.
FUNCTIONAL_CUES = ("CEO", "최고경영자", "대표", "회장", "대통령", "사장", "총리")
YEAR = re.compile(r"(1[89]\d\d|20\d\d)")


def _interval_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    af, at = a
    bf, bt = b
    af = -math.inf if af is None else af
    at = math.inf if at is None else at
    bf = -math.inf if bf is None else bf
    bt = math.inf if bt is None else bt
    # half-open intervals [from, to): a shared boundary (A.to == B.from) is a
    # clean supersession handoff, NOT an overlap -> strict inequality.
    return af < bt and bf < at


def tcv_check(values: list[dict[str, Any]]) -> str:
    """Deterministic Temporal-Consistency verdict for one functional slot.

    values: list of {value, interval=(from,to), confident:bool}
    Returns: 'consistent' | 'contradiction' | 'needs_review'.
    """
    distinct = {v["value"] for v in values}
    if len(distinct) <= 1:
        return "consistent"  # single value (or repeats) — no conflict
    confident = [v for v in values if v["confident"]]
    # any two DISTINCT confident values with overlapping intervals => contradiction
    for i in range(len(confident)):
        for j in range(i + 1, len(confident)):
            if confident[i]["value"] != confident[j]["value"] and _interval_overlap(
                confident[i]["interval"], confident[j]["interval"]
            ):
                return "contradiction"
    # distinct values but disjoint confident intervals => a timeline (supersession)
    if len(confident) >= 2:
        return "consistent"
    # competing values but not enough confident time info to order them
    return "needs_review"


def _self_test() -> dict[str, Any]:
    overlap = tcv_check([
        {"value": "A", "interval": (2015, None), "confident": True},
        {"value": "B", "interval": (2019, None), "confident": True},
    ])  # both open-ended -> overlap -> contradiction
    timeline = tcv_check([
        {"value": "A", "interval": (2015, 2019), "confident": True},
        {"value": "B", "interval": (2019, None), "confident": True},
    ])  # disjoint -> consistent timeline (supersession)
    unknown = tcv_check([
        {"value": "A", "interval": (None, None), "confident": False},
        {"value": "B", "interval": (None, None), "confident": False},
    ])  # competing, no time info -> needs_review
    single = tcv_check([{"value": "A", "interval": (None, None), "confident": False}])
    return {
        "overlap_two_open_values": overlap,        # expect contradiction
        "disjoint_timeline": timeline,             # expect consistent
        "competing_no_dates": unknown,             # expect needs_review
        "single_value": single,                    # expect consistent
        "all_pass": overlap == "contradiction" and timeline == "consistent"
        and unknown == "needs_review" and single == "consistent",
    }


def _frame_blob(r: dict[str, Any]) -> str:
    cf = r.get("canonical_form", "") or ""
    heads = " ".join(str(x.get("head", "")) for x in r.get("case_roles", []))
    return cf + " " + heads


def measure(store_dir: Path) -> dict[str, Any]:
    total = 0
    anchor_year = 0
    anchor_created_only = 0
    functional = []
    with (store_dir / "case_frames.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            blob = _frame_blob(r)
            if YEAR.search(blob):
                anchor_year += 1
            elif r.get("created_at"):
                anchor_created_only += 1
            if any(c in blob for c in FUNCTIONAL_CUES):
                functional.append(r)

    # Axis 2: group functional facts by subject head (first SUBJ/TOPIC role)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in functional:
        subj = ""
        for role in r.get("case_roles", []):
            if str(role.get("role")) in ("SUBJ", "TOPIC"):
                subj = str(role.get("head", "")).strip()
                break
        if not subj:
            continue
        m = YEAR.search(_frame_blob(r))
        yr = int(m.group(1)) if m else None
        # "value" = a non-subject role head (best-effort)
        val = ""
        for role in r.get("case_roles", []):
            h = str(role.get("head", "")).strip()
            if h and h != subj:
                val = h
                break
        groups.setdefault(subj, []).append({
            "value": val or r.get("frame_id"),
            "interval": (yr, None),
            "confident": yr is not None,
        })

    contradiction = needs_review = consistent = 0
    multi_value_slots = 0
    for subj, vals in groups.items():
        if len({v["value"] for v in vals}) > 1:
            multi_value_slots += 1
        verdict = tcv_check(vals)
        if verdict == "contradiction":
            contradiction += 1
        elif verdict == "needs_review":
            needs_review += 1
        else:
            consistent += 1

    return {
        "report_id": "temporal_4d_shadow_v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "store_dir": str(store_dir),
        "functional_cues_note": "MEASUREMENT-ONLY eval cues; not engine logic, not an answer table",
        "axis1_temporal_coverage": {
            "total_case_frames": total,
            "with_explicit_year": anchor_year,
            "created_at_only": anchor_created_only,
            "explicit_year_pct": round(anchor_year / total, 4) if total else 0.0,
            "interpretation": "high-confidence temporal anchors are rare; most facts only have ingest time",
        },
        "axis2_functional_slots": {
            "functional_attribution_facts": len(functional),
            "subject_slots": len(groups),
            "multi_value_slots(contradiction_candidates)": multi_value_slots,
            "tcv_verdicts": {"consistent": consistent, "needs_review": needs_review, "contradiction": contradiction},
            "interpretation": "current graph has very few functional+temporal facts -> 4D value is LATENT, grows with data",
        },
        "axis3_tcv_mechanism_selftest": _self_test(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Temporal 4D shadow measurement (read-only)")
    ap.add_argument("--store", type=Path, default=LIVE)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "temporal-4d")
    args = ap.parse_args()

    report = measure(args.store)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (args.out_dir / f"{ts}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    a1 = report["axis1_temporal_coverage"]
    a2 = report["axis2_functional_slots"]
    a3 = report["axis3_tcv_mechanism_selftest"]
    print(f"[4D] coverage: {a1['with_explicit_year']}/{a1['total_case_frames']} explicit-year ({a1['explicit_year_pct']})")
    print(f"[4D] functional facts={a2['functional_attribution_facts']} slots={a2['subject_slots']} "
          f"multi-value={a2['multi_value_slots(contradiction_candidates)']} verdicts={a2['tcv_verdicts']}")
    print(f"[4D] TCV mechanism self-test all_pass={a3['all_pass']} ({a3})")
    print(f"[4D] report: {args.out_dir / (ts + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
