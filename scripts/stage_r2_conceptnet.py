# -*- coding: utf-8 -*-
"""Stage the FULL English promotable ConceptNet 5.7 set into a SCOPED staging store
to validate the R2 graph-density root lever (2026-07-23).

WHY: every fluency/knowledge cap traced to GRAPH DENSITY. Only ~0.058% of the shipped
store's ~1.4M subjects carry a promotable functional relation (capable_of / has_a /
used_for), because the shipped store holds only a tiny fraction of ConceptNet's promotable
edges (~2,659 capable_of vs ConceptNet's ~22,677 English). This script re-extracts the FULL
English promotable set from the LOCAL dump and lands it in a SEPARATE staging store so the
density lift can be measured.

SAFETY: this NEVER writes the shipped kg_triples store. It writes only to
data/graph_scale/staging_r2_conceptnet/. Promotion staging->shipped is the operator-signed
morning step (candidate_promotion_gate); this stages + measures only.

ENGLISH-ONLY: keeps only /c/en/ on BOTH endpoints (Korean is /c/ko/, so the output is
Hangul-free by construction; a Hangul regex re-asserts it). Predicate names are aligned to
the SHIPPED store's own convention (verified via its term dict: has_a=35739 not has_part;
made_of=93936 english) so a future promotion merges cleanly.

NO FABRICATION: every staged edge is a real ConceptNet 5.7 assertion, provenance
conceptnet-5.7. Gates mirror the original harvest (conceptnet_connector.harvest_from_dump):
weight>=1.0, s!=o, surface<=40 chars, deduped.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

_MEMBRANE_TRUTHY = {"1", "true", "yes", "on"}

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from packages.graph_scale.triple_store import TripleStore  # noqa: E402

DUMP = REPO / "data" / "graph_scale" / "conceptnet_dump" / "conceptnet-assertions-5.7.0.csv.gz"
STAGING = REPO / "data" / "graph_scale" / "staging_r2_conceptnet"

# /r/* -> our predicate, aligned to the SHIPPED store's naming.
RELMAP = {
    "/r/CapableOf": "capable_of",
    "/r/UsedFor": "used_for",
    "/r/HasA": "has_a",
    "/r/PartOf": "part_of",
    "/r/MadeOf": "made_of",
    "/r/HasProperty": "has_property",
    "/r/IsA": "is_a",
}
# the promotable FUNCTIONAL set (task R2 lift target); is_a is the taxonomic backbone, staged
# too but reported separately (it is the composed-fire cross-check partner, not the lift metric).
FUNCTIONAL = {"capable_of", "used_for", "has_a", "part_of", "made_of", "has_property"}
MIN_WEIGHT = 1.0
HANGUL = re.compile(r"[가-힣]")


def label(uri: str) -> tuple[str, str]:
    """'/c/en/new_york_city' -> ('en', 'new york city')."""
    p = uri.strip("/").split("/")
    if len(p) >= 3 and p[0] == "c":
        return p[1], p[2].replace("_", " ").strip()
    return "", ""


def main() -> int:
    if not DUMP.exists():
        print("DUMP NOT FOUND:", DUMP)
        return 2
    if STAGING.exists():
        import shutil
        shutil.rmtree(STAGING)  # fresh staging each run so counts are exact

    store = TripleStore(STAGING, dict_backend="ram")
    src_id = store.intern_source("conceptnet-5.7", "https://conceptnet.io/c/en/{s}")

    # firewall membrane: opt-in via ATANOR_MEMBRANE_LIVE (no CLI here). Flag OFF -> no import,
    # no-op, so staging behaves exactly as today. Observe-only: the staging store is unchanged.
    fp = None
    if os.environ.get("ATANOR_MEMBRANE_LIVE", "").strip().lower() in _MEMBRANE_TRUTHY:
        from packages.truth_maintenance.live_membrane import FirewallStagePass  # noqa: E402
        fp = FirewallStagePass(provenance="conceptnet-5.7")

    seen_rows = 0
    per_rel_added: Counter[str] = Counter()
    per_rel_dup: Counter[str] = Counter()
    dropped_hangul = 0
    dropped_filters = 0
    func_subjects: set[str] = set()
    t0 = time.time()
    with gzip.open(DUMP, "rt", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            seen_rows += 1
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            pred = RELMAP.get(cols[1])
            if not pred:
                continue
            ls, s = label(cols[2])
            lo, o = label(cols[3])
            if ls != "en" or lo != "en":          # ENGLISH-ONLY on both endpoints
                continue
            if not s or not o or s == o:
                dropped_filters += 1
                continue
            if len(s) > 40 or len(o) > 40:         # drop long noisy phrases (harvest parity)
                dropped_filters += 1
                continue
            try:
                w = float(json.loads(cols[4]).get("weight", 1.0))
            except Exception:
                w = 1.0
            if w < MIN_WEIGHT:                     # drop weak crowd edges
                dropped_filters += 1
                continue
            if HANGUL.search(s) or HANGUL.search(o):  # defensive; en-en already excludes Hangul
                dropped_hangul += 1
                continue
            if store.add(s, pred, o, source=src_id):
                per_rel_added[pred] += 1
                if pred in FUNCTIONAL:
                    func_subjects.add(s)
                if fp is not None:                     # firewall membrane (observe-only)
                    fp.observe(s, pred, o)
            else:
                per_rel_dup[pred] += 1
            if seen_rows % 5_000_000 == 0:
                print(f"...scanned {seen_rows:,}  added={sum(per_rel_added.values()):,}  "
                      f"{time.time() - t0:.0f}s", flush=True)

    store.flush()
    store.terms.flush()
    store.rebuild_index()

    functional_added = sum(per_rel_added[r] for r in FUNCTIONAL)
    manifest = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dump": str(DUMP),
        "provenance": "conceptnet-5.7",
        "english_only": "both endpoints /c/en/",
        "gates": {"min_weight": MIN_WEIGHT, "max_surface_len": 40, "drop_self_loops": True},
        "rows_scanned": seen_rows,
        "added_per_relation": dict(per_rel_added),
        "duplicates_per_relation": dict(per_rel_dup),
        "dropped_hangul": dropped_hangul,
        "dropped_filters": dropped_filters,
        "functional_relations": sorted(FUNCTIONAL),
        "functional_edges_added": functional_added,
        "isa_edges_added": per_rel_added.get("is_a", 0),
        "total_edges": len(store),
        "distinct_functional_subjects": len(func_subjects),
        "elapsed_s": round(time.time() - t0, 1),
    }
    (STAGING / "R2_STAGING_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    # firewall membrane manifest written OUT-OF-TREE (never data/graph_scale) when opt-in
    if fp is not None:
        from packages.truth_maintenance.live_membrane import default_firewall_out, write_manifest
        out = write_manifest(fp, default_firewall_out("r2_conceptnet"))
        print(f"[firewall] membrane manifest -> {out}  "
              f"(observed={fp.observed} passed={fp.passed} quarantined={len(fp.quarantined)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
