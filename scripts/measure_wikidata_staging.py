# -*- coding: utf-8 -*-
"""MEASURE the S1 Wikidata staging store — READ-ONLY, prints a report, WRITES NOTHING.

This is step 1 of the S1 landing chain: the operator runs it AFTER S1 finishes and reads the
report BEFORE deciding to promote. It answers, for the staged store:
  1. is it complete (safe to read) or still mid-write?
  2. total edge count;
  3. per-relation distribution (top 20);
  4. English-only verification — Hangul / non-ASCII terms (should be ~0), with violators;
  5. contamination spot-check — a sample of staged triples for eyeball audit, each traced to
     its provenance source line + a structural plausibility check;
  6. density-lift — staged vs current shipped edge counts and per-relation net-new deltas
     (e.g. capital: shipped N -> +M);
  7. (optional) firewall T0 nogood pre-check, if a T0 seed is supplied.

SAFETY: opens both stores read-only (mode=ro sqlite + np.fromfile columns). It cannot mutate
either store, and it never co-writes data/graph_scale. By default it REFUSES an incomplete
(mid-write) staging store — measure only after S1 has finished and finalized.

  python scripts/measure_wikidata_staging.py \
      [--staging data/graph_scale/staging_b1_wikidata] \
      [--shipped data/graph_scale/kg_triples] [--sample 50] \
      [--t0 runtime/firewall/t0_axioms.json --firewall] [--allow-incomplete]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import landing_chain_lib as L  # noqa: E402

DEF_STAGING = REPO / "data" / "graph_scale" / "staging_b1_wikidata"
DEF_SHIPPED = REPO / "data" / "graph_scale" / "kg_triples"


def _rule(title: str) -> None:
    print("=" * 78)
    print(title)


def contamination_spotcheck(staged: L.ReadOnlyStore, shipped: L.ReadOnlyStore,
                            n: int, seed: int = 0) -> dict:
    """Sample n staged edges; decode to strings; trace each to its provenance source line and
    run a structural plausibility check (predicate is a known shipped predicate; endpoints are
    non-empty English strings). HONEST: without the multi-GB raw Wikidata dump mounted here, a
    byte-for-byte dump-line replay is out of scope — this verifies PROVENANCE + STRUCTURE, which
    is what catches a contaminated or mis-mapped staged edge."""
    s = staged.col("s"); p = staged.col("p"); o = staged.col("o"); src = staged.col("src")
    src_lines = staged.source_lines()
    shipped_preds = set(shipped.predicate_counts().keys())
    n_edges = len(s)
    rng = np.random.default_rng(seed)
    idx = rng.choice(n_edges, size=min(n, n_edges), replace=False) if n_edges else np.zeros(0, int)
    rows = []
    non_wikidata = 0
    unknown_pred = 0
    non_english = 0
    for i in idx.tolist():
        subj = staged.term(int(s[i])); pred = staged.term(int(p[i])); obj = staged.term(int(o[i]))
        src_id = int(src[i]) if i < len(src) else 0
        src_line = src_lines[src_id] if 0 <= src_id < len(src_lines) else "(unknown)"
        prov = src_line.split("|", 1)[0]
        pred_known = pred in shipped_preds
        eng = subj.isascii() and obj.isascii()
        if "wikidata" not in prov.lower():
            non_wikidata += 1
        if not pred_known:
            unknown_pred += 1
        if not eng:
            non_english += 1
        rows.append({"s": subj, "p": pred, "o": obj, "provenance": prov,
                     "pred_in_shipped_vocab": pred_known, "english": eng})
    return {"sampled": len(rows), "rows": rows,
            "flags": {"non_wikidata_provenance": non_wikidata,
                      "predicate_not_in_shipped_vocab": unknown_pred,
                      "non_english_endpoint": non_english}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(DEF_STAGING))
    ap.add_argument("--shipped", default=str(DEF_SHIPPED))
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--t0", default="", help="T0 axiom seed json (build_t0_axioms.py output)")
    ap.add_argument("--firewall", action="store_true", help="run the T0 nogood pre-check")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="measure even if the staging store looks mid-write (numbers unreliable)")
    args = ap.parse_args()

    staging_root = Path(args.staging)
    shipped_root = Path(args.shipped)

    _rule(f"S1 STAGING MEASUREMENT  (READ-ONLY; writes nothing)")
    print(f"  staging: {staging_root}")
    print(f"  shipped: {shipped_root}")

    # 1) completeness
    _rule("1. COMPLETENESS")
    ok, det = L.store_completeness(staging_root)
    print(json.dumps(det, indent=2, ensure_ascii=False))
    if not ok and not args.allow_incomplete:
        print("\nREFUSING: staging store looks incomplete / mid-write. Measure only after S1 has\n"
              "finished and finalized (meta.count == s.col rows == p.col == o.col). Re-run with\n"
              "--allow-incomplete only if you understand the numbers may be torn.")
        return 3
    if not ok:
        print("\nWARNING: proceeding on an INCOMPLETE store (--allow-incomplete). Numbers unreliable.")

    staged = L.ReadOnlyStore(staging_root)
    shipped = L.ReadOnlyStore(shipped_root)
    try:
        # 2) totals
        _rule("2. TOTALS")
        print(f"  staged edges : {staged.n_edges:,}")
        print(f"  staged terms : {staged.n_terms:,}")
        print(f"  shipped edges: {shipped.n_edges:,}")
        print(f"  shipped terms: {shipped.n_terms:,}")

        # 3) per-relation distribution (top N)
        _rule(f"3. STAGED PER-RELATION DISTRIBUTION (top {args.top})")
        pc = staged.predicate_counts()
        for pred, c in pc.most_common(args.top):
            print(f"  {c:>12,}  {pred}")
        print(f"  ... {len(pc)} distinct predicates total")

        # 4) English-only verification
        _rule("4. ENGLISH-ONLY VERIFICATION (staged term dictionary)")
        eng = L.scan_english_only(staged)
        print(f"  terms scanned   : {eng['terms_scanned']:,}")
        print(f"  Hangul terms    : {eng['hangul_terms']:,}   (HARD FAIL if > 0)")
        print(f"  non-ASCII terms : {eng['non_ascii_terms']:,}   (report-only)")
        if eng["hangul_samples"]:
            print(f"  Hangul samples  : {eng['hangul_samples']}")
        if eng["non_ascii_samples"]:
            print(f"  non-ASCII sample: {eng['non_ascii_samples'][:15]}")
        print(f"  english_only_ok : {eng['english_only_ok']}")

        # 5) contamination spot-check
        _rule(f"5. CONTAMINATION SPOT-CHECK ({args.sample} sampled staged triples)")
        spot = contamination_spotcheck(staged, shipped, args.sample)
        for r in spot["rows"]:
            flag = "" if (r["pred_in_shipped_vocab"] and r["english"]) else "  <-- REVIEW"
            print(f"  ({r['s']}) --{r['p']}--> ({r['o']})   [{r['provenance']}]{flag}")
        print(f"  flags: {spot['flags']}")
        print("  NOTE: provenance + structural trace (predicate in shipped vocab, English "
              "endpoints).\n        Byte-for-byte raw-dump replay is out of scope without the "
              "Wikidata dump mounted.")

        # 6) density-lift (the promotion projection — READ-ONLY)
        _rule("6. DENSITY LIFT  (staged vs shipped, exact dedup, per relation)")
        plan = L.plan_merge(staging_root, shipped_root)
        print(f"  new terms staging adds : {plan['n_new_terms']:,}")
        t = plan["totals"]
        print(f"  staged distinct edges  : {t['staged_distinct']:,}")
        print(f"  duplicates of shipped  : {t['duplicates']:,}")
        print(f"  NET-NEW edges          : {t['net_new']:,}")
        print(f"  shipped now            : {plan['shipped_edges']:,}")
        print(f"  shipped after promote  : {t['projected_shipped_after']:,}")
        print("  per-relation (shipped -> +net_new):")
        for pred, d in list(plan["per_relation"].items())[:max(args.top, 25)]:
            print(f"    {pred:<24} shipped {d['shipped']:>10,} -> +{d['net_new']:<10,}  "
                  f"(staged {d['staged_distinct']:,}, dup {d['duplicates']:,})")

        # 7) firewall T0 nogood (optional)
        if args.firewall:
            _rule("7. FIREWALL T0 NOGOOD PRE-CHECK")
            if not args.t0 or not Path(args.t0).exists():
                print("  --firewall requested but no valid --t0 seed given; skipping.")
            else:
                t0 = json.loads(Path(args.t0).read_text(encoding="utf-8"))
                facts = [tuple(f) for f in t0.get("facts", [])]
                prov = t0.get("provenance", "wikidata-truthy")
                fw = L.firewall_nogood_check(staging_root, prov, facts)
                print(f"  T0 axioms seeded : {len(facts):,}")
                print(f"  staged edges checked (T0-relevant predicates): {fw['observed']:,}")
                print(f"  passed           : {fw['passed']:,}")
                print(f"  QUARANTINED      : {len(fw['quarantined']):,}")
                for q in fw["quarantined"][:30]:
                    print(f"    NOGOOD: {q['predicate']}({q['subject']})={q['object']}  "
                          f"contradicts {q['contradicts']}")

        _rule("DONE — nothing was written. Review, then run promote_staging_to_shipped.py.")
        return 0
    finally:
        staged.close()
        shipped.close()


if __name__ == "__main__":
    raise SystemExit(main())
