# -*- coding: utf-8 -*-
"""BUILD the firewall T0 operator-axiom seed for the S1 landing chain.

The live-membrane nogood pre-check (packages/truth_maintenance/live_membrane.FirewallStagePass)
quarantines a staged edge that CONTRADICTS a seeded T0/operator fact on a FUNCTIONAL predicate.
"Functional" (packages/truth_maintenance/revision.DEFAULT_FUNCTIONAL) means at most one object
per subject — a country has ONE capital — so `capital(France)=Lyon` clashes with the axiom
`capital(France)=Paris` and is caught. Non-functional predicates (is_a, located_in-as-multivalue)
never trigger a nogood and are NOT harvested here.

WHERE THE AXIOMS COME FROM (not a code table — owner BINDING rule 1)
-------------------------------------------------------------------
This does NOT hardcode a capital list. It HARVESTS axioms FROM THE SHIPPED GRAPH: every subject
that carries a functional predicate with EXACTLY ONE distinct object in the store (unambiguous =
already high-confidence) becomes an axiom. Ambiguous subjects (2+ objects on a functional
predicate = dirty/contested) are dropped, not guessed. The output is the operator's integrity
constraints, derived from facts the store already vouches for.

HONEST SCOPE
------------
This is a SEED, not an exhaustive contradiction oracle. By default it harvests only `capital`
(the cleanest single-valued relation, subject=country -> object=capital-city, verified via the
shipped store's own answer templates). The operator EXTENDS it by:
  * adding predicates via --predicates (e.g. capital_of, born_in, atomic_number) — but ONLY
    genuinely single-valued ones; `located_in` is in DEFAULT_FUNCTIONAL yet is granularity-
    multivalued in real data (a city is located_in a region AND its country), so harvesting it
    would manufacture false conflicts — excluded by default, add only with curation;
  * hand-editing the emitted JSON to add operator-asserted facts not yet in the graph;
  * re-running after the store grows.

READ-ONLY: opens the source store mode=ro; writes only the out-of-tree seed JSON (default
runtime/firewall/t0_axioms.json). Never writes any store, never co-writes data/graph_scale.

  python scripts/build_t0_axioms.py [--store data/graph_scale/kg_triples] \
      [--predicates capital] [--out runtime/firewall/t0_axioms.json] [--max 5000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
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

DEF_STORE = REPO / "data" / "graph_scale" / "kg_triples"
DEF_OUT = REPO / "runtime" / "firewall" / "t0_axioms.json"

# functional (single-valued) predicates that are SAFE to seed as contradiction axioms.
# Kept deliberately narrow; see the module docstring for why located_in is excluded.
SAFE_FUNCTIONAL_DEFAULT = ["capital"]


def harvest_axioms(store: L.ReadOnlyStore, predicates: list[str],
                   *, max_facts: int = 0) -> tuple[list[list[str]], dict]:
    """Return (facts, stats). A fact (s, p, o) is emitted iff subject s has EXACTLY ONE distinct
    object o on functional predicate p in the store (unambiguous), s != o, and both are English."""
    s_col = store.col("s"); p_col = store.col("p"); o_col = store.col("o")
    facts: list[list[str]] = []
    stats: dict = {}
    for pred in predicates:
        pid = store.pid(pred)
        if pid is None:
            stats[pred] = {"predicate_present": False, "axioms": 0}
            continue
        mask = p_col == pid
        s_ids = s_col[mask]
        o_ids = o_col[mask]
        # group objects per subject
        by_subj: dict[int, set[int]] = defaultdict(set)
        for s, o in zip(s_ids.tolist(), o_ids.tolist()):
            by_subj[s].add(o)
        n_ambiguous = 0
        n_emitted = 0
        for s, os in by_subj.items():
            if len(os) != 1:
                n_ambiguous += 1
                continue
            o = next(iter(os))
            subj = store.term(int(s)); obj = store.term(int(o))
            if not subj or not obj or subj == obj:
                continue
            if not (subj.isascii() and obj.isascii()):  # English-only axioms
                continue
            facts.append([subj, pred, obj])
            n_emitted += 1
        stats[pred] = {"predicate_present": True, "distinct_subjects": len(by_subj),
                       "ambiguous_dropped": n_ambiguous, "axioms": n_emitted}
    if max_facts and len(facts) > max_facts:
        facts = facts[:max_facts]
    return facts, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(DEF_STORE))
    ap.add_argument("--predicates", nargs="*", default=SAFE_FUNCTIONAL_DEFAULT)
    ap.add_argument("--out", default=str(DEF_OUT))
    ap.add_argument("--provenance", default="wikidata-truthy",
                    help="provenance tag the T0 set will be checked against")
    ap.add_argument("--max", type=int, default=0, help="cap number of axioms (0 = no cap)")
    args = ap.parse_args()

    store_root = Path(args.store)
    print("=" * 78)
    print(f"BUILD T0 AXIOMS  (READ-ONLY harvest from {store_root})")
    print(f"  predicates: {args.predicates}")

    store = L.ReadOnlyStore(store_root)
    try:
        facts, stats = harvest_axioms(store, args.predicates, max_facts=args.max)
    finally:
        store.close()

    seed = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_store": str(store_root),
        "provenance": args.provenance,
        "predicates": args.predicates,
        "n_axioms": len(facts),
        "per_predicate": stats,
        "note": ("SEED, not exhaustive. Harvested from the shipped graph: subjects with exactly "
                 "one object on a functional predicate. Operator extends via --predicates (only "
                 "genuinely single-valued relations; NOT located_in), by hand-editing facts[], "
                 "or by re-running after the store grows."),
        "facts": facts,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    for pred, st in stats.items():
        print(f"  {pred:<16} {st}")
    print(f"  TOTAL axioms: {len(facts)}")
    if facts[:8]:
        print("  sample:")
        for f in facts[:8]:
            print(f"    {f[1]}({f[0]}) = {f[2]}")
    print(f"  written -> {out}")
    print("=" * 78)
    print("Extend: add curated single-valued predicates via --predicates, or hand-edit facts[].")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
