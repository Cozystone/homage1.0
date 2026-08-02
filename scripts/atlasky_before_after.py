#!/usr/bin/env python3
"""ATLASky before/after efficiency measurement (READ-ONLY, NON-DESTRUCTIVE).

Quantifies what adopting the ATLASky RMMVe cascade adds over the current binary
gate. HONESTY: there are no ground-truth correctness labels for live candidates,
so this does NOT claim an accuracy %. It measures three honest efficiency axes:

  A. Pre-integration triage  — of candidates the binary gate VERIFIES, how many
     does the cascade route to review (weakly grounded) BEFORE integration?
     (ATLASky's "verify-before-integrate / lower error" value.)
  B. Compute / early-termination (PROJECTED) — fraction of candidates the cheap
     LOV module resolves alone, which would skip the 3 expensive deferred modules
     (POV/WSV/phase). Projected module-eval saving. Labeled as projection because
     those modules are not built yet.
  C. Labeled mis-routing — on the 60-Q labeled fixture, naive derivation routing
     ("derivation fired -> route") vs cascade promotion, on the NEGATIVE labels
     that must never route. (ATLASky's error-rate-reduction analog.)

Nothing is written to any store; only a report under reports/atlasky-ba/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import derivation_p0_audit as dp0       # noqa: E402
import rmmve_shadow_scorer as rss       # noqa: E402
import shadow_attach_ingest as sai      # noqa: E402
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence       # noqa: E402
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence           # noqa: E402
from packages.cloud_brain.continuous_learning import source_sentence_from_payload  # noqa: E402

NEGATIVE_LABELS = ("alias_or_failure_negative", "non_attribution_distractor", "abstain_expected")
N_DEFERRED_EXPENSIVE = 3   # POV, WSV, phase_resonance
N_TOTAL_MODULES = 5        # full RMMVe


def axis_a_b(limit: int) -> dict[str, Any]:
    store = dp0.load_store_predicates(sai.LIVE)
    names = rss._load_concept_names(sai.LIVE)
    payloads = sai.build_payloads(limit)

    before_verified = 0
    before_rejected = 0
    after = {"would_promote": 0, "would_flag": 0, "would_abstain": 0}
    lov_early_eligible = 0   # cheap module alone clears -> would skip expensive ones
    scored_candidates = 0
    dedupe: set[str] = set()

    for pl in payloads:
        s = source_sentence_from_payload(pl)
        dec = verify_sentence(s, existing_dedupe_keys=dedupe)
        if dec.status != "verified":
            before_rejected += 1
            continue
        before_verified += 1
        result = decompose_sentence(s, dec, ingest_run_id="atlasky_ba")
        scored = [sai._score_frame(f, store, names) for f in result.case_frames]
        best = max(scored, key=lambda x: x["ctotal"]) if scored else None
        decision, _ = sai._decide(best)
        after[decision] = after.get(decision, 0) + 1
        if best is not None:
            scored_candidates += 1
            if best["c_lov"] >= rss.THETA_LOV:
                lov_early_eligible += 1

    caught = after["would_flag"] + after["would_abstain"]
    triage_rate = round(caught / before_verified, 4) if before_verified else 0.0
    # projected compute saving: on early-eligible candidates, skip 3/5 modules.
    proj_saving = round((lov_early_eligible / scored_candidates) * (N_DEFERRED_EXPENSIVE / N_TOTAL_MODULES), 4) if scored_candidates else 0.0

    return {
        "candidates": before_verified + before_rejected,
        "before_gate": {"would_integrate(verified)": before_verified, "rejected": before_rejected},
        "after_cascade": after,
        "axis_A_triage": {
            "verified_by_binary_gate": before_verified,
            "cascade_promotes": after["would_promote"],
            "cascade_routes_to_review_before_integration": caught,
            "triage_rate": triage_rate,
            "meaning": "fraction of would-be integrations the cascade flags for review first (grounding strength, NOT verified-correctness)",
        },
        "axis_B_compute_projection": {
            "scored_candidates": scored_candidates,
            "resolved_by_cheap_LOV_alone": lov_early_eligible,
            "projected_expensive_module_eval_saving": proj_saving,
            "note": "PROJECTION: POV/WSV/phase are deferred/not-built; this is the saving early-termination WOULD give once they exist",
        },
    }


def axis_c_labeled() -> dict[str, Any]:
    fixture = dp0.DEFAULT_FIXTURE
    # BEFORE = naive routing: P0 "derivation fired" -> would route
    p0 = dp0.run_audit(fixture, dp0.DEFAULT_STORE)
    before_route_neg = 0
    neg_total = 0
    for q in p0["per_question"]:
        if q["label"] in NEGATIVE_LABELS:
            neg_total += 1
            if q["derived"] is not None:
                before_route_neg += 1
    # AFTER = cascade promotion
    cas = rss.run(fixture, dp0.DEFAULT_STORE)
    after_promote_neg = sum(
        1 for q in cas["per_question"]
        if q["label"] in NEGATIVE_LABELS and q["decision"] == "would_promote"
    )
    prod_total = sum(1 for q in cas["per_question"] if q["label"] == "productive_derivation_probe")
    after_promote_prod = sum(
        1 for q in cas["per_question"]
        if q["label"] == "productive_derivation_probe" and q["decision"] == "would_promote"
    )
    return {
        "negative_label_questions": neg_total,
        "before_naive_routing_misroutes_negatives": before_route_neg,
        "before_misroute_rate": round(before_route_neg / neg_total, 4) if neg_total else 0.0,
        "after_cascade_promotes_negatives": after_promote_neg,
        "after_misroute_rate": round(after_promote_neg / neg_total, 4) if neg_total else 0.0,
        "productive_promoted_after": f"{after_promote_prod}/{prod_total}",
        "meaning": "on labeled negatives that must NEVER route, naive derivation routing vs cascade promotion",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ATLASky before/after efficiency (read-only)")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "atlasky-ba")
    args = ap.parse_args()

    ab = axis_a_b(args.limit)
    c = axis_c_labeled()
    report = {
        "measurement_id": "atlasky_before_after_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "store_mutated": False,
        "honesty_caveat": "No ground-truth correctness labels on live candidates; this measures grounding-triage + projected compute, NOT an accuracy percentage.",
        "axis_A_and_B": ab,
        "axis_C_labeled_misrouting": c,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (args.out_dir / f"{ts}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    A = ab["axis_A_triage"]; B = ab["axis_B_compute_projection"]
    print(f"[BA] candidates={ab['candidates']}  binary-gate verified={A['verified_by_binary_gate']}")
    print(f"[BA] AXIS A triage: cascade promotes {A['cascade_promotes']}, routes {A['cascade_routes_to_review_before_integration']} to review (rate {A['triage_rate']})")
    print(f"[BA] AXIS B compute(proj): {B['resolved_by_cheap_LOV_alone']}/{B['scored_candidates']} resolved by cheap LOV -> projected expensive-module saving {B['projected_expensive_module_eval_saving']}")
    print(f"[BA] AXIS C labeled: before misroutes {c['before_naive_routing_misroutes_negatives']}/{c['negative_label_questions']} negatives ({c['before_misroute_rate']}) -> after {c['after_cascade_promotes_negatives']} ({c['after_misroute_rate']})")
    print(f"[BA] report: {args.out_dir / (ts + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
