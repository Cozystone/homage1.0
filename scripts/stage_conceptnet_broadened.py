# -*- coding: utf-8 -*-
"""Broadened ConceptNet 5.7 English ingest -> a FRESH scoped staging store (2026-07-24).

WHY: the earlier stage_r2_conceptnet.py landed the 7-relation functional/taxonomic set. This adds
three MORE promotable relations that map to EXISTING shipped predicates (so ZERO new vocab, ZERO
speech-frame debt) and are exactly the propositional shapes MMLU-style conceptual MCQ leans on:
  /r/AtLocation -> located_in   (spatial grounding)
  /r/DefinedAs  -> defined_as   (definitional grounding -> feeds the openbook/define path)
  /r/Antonym    -> antonym      (contrast grounding -> feeds negated 'which is NOT' discrimination)
plus the original 7 (is_a, capable_of, used_for, has_a, part_of, made_of, has_property).

SAFETY / BINDING (identical to stage_r2_conceptnet.py):
  * NEVER writes the shipped store. Writes ONLY to data/graph_scale/staging_r2_conceptnet_v2/.
    Promotion staging->shipped is the operator-signed step (promote_staging_to_shipped.py).
  * ENGLISH-ONLY: both endpoints /c/en/ (Hangul-free by construction + a defensive regex).
  * NO FABRICATION: every edge is a real ConceptNet 5.7 assertion, provenance conceptnet-5.7.
  * Every target predicate is an EXISTING shipped predicate WITH a speech frame (verified live:
    facts_about returns is_a/located_in/defined_as/antonym/has_property... rows today), so a future
    promotion merges with no new vocab and no fluency-doctrine debt.

  python -X utf8 scripts/stage_conceptnet_broadened.py
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from packages.graph_scale.triple_store import TripleStore  # noqa: E402

DUMP = REPO / "data" / "graph_scale" / "conceptnet_dump" / "conceptnet-assertions-5.7.0.csv.gz"
if not DUMP.exists():
    DUMP = REPO / "data" / "graph_scale" / "conceptnet-assertions-5.7.0.csv.gz"
STAGING = REPO / "data" / "graph_scale" / "staging_r2_conceptnet_v2"

RELMAP = {
    "/r/IsA": "is_a",
    "/r/CapableOf": "capable_of",
    "/r/UsedFor": "used_for",
    "/r/HasA": "has_a",
    "/r/PartOf": "part_of",
    "/r/MadeOf": "made_of",
    "/r/HasProperty": "has_property",
    "/r/AtLocation": "located_in",   # NEW vs r2
    "/r/DefinedAs": "defined_as",    # NEW vs r2
    "/r/Antonym": "antonym",         # NEW vs r2
}
MIN_WEIGHT = 1.0
MAX_SURFACE = 40
HANGUL = re.compile(r"[가-힣]")


def label(uri: str) -> tuple[str, str]:
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
        shutil.rmtree(STAGING)
    # sharded backend (term_shards/) so the S1 safe promoter (promote_staging_to_shipped.py) can
    # build_term_map against it — the operator-signed landing chain requires the sharded form.
    store = TripleStore(STAGING, dict_backend="sharded")
    src_id = store.intern_source("conceptnet-5.7", "https://conceptnet.io/c/en/{s}")

    seen = 0
    per_rel_added: Counter[str] = Counter()
    per_rel_dup: Counter[str] = Counter()
    dropped_hangul = dropped_filters = 0
    t0 = time.time()
    with gzip.open(DUMP, "rt", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            seen += 1
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            pred = RELMAP.get(cols[1])
            if not pred:
                continue
            ls, s = label(cols[2])
            lo, o = label(cols[3])
            if ls != "en" or lo != "en":
                continue
            if not s or not o or s == o or len(s) > MAX_SURFACE or len(o) > MAX_SURFACE:
                dropped_filters += 1
                continue
            try:
                w = float(json.loads(cols[4]).get("weight", 1.0))
            except Exception:
                w = 1.0
            if w < MIN_WEIGHT:
                dropped_filters += 1
                continue
            if HANGUL.search(s) or HANGUL.search(o):
                dropped_hangul += 1
                continue
            if store.add(s, pred, o, source=src_id):
                per_rel_added[pred] += 1
            else:
                per_rel_dup[pred] += 1
            if seen % 5_000_000 == 0:
                print(f"...scanned {seen:,} added={sum(per_rel_added.values()):,} "
                      f"{time.time()-t0:.0f}s", flush=True)

    store.flush()
    store.terms.flush()
    store.rebuild_index()
    manifest = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dump": str(DUMP),
        "provenance": "conceptnet-5.7",
        "english_only": "both endpoints /c/en/",
        "new_relations_vs_r2": ["located_in", "defined_as", "antonym"],
        "gates": {"min_weight": MIN_WEIGHT, "max_surface_len": MAX_SURFACE, "drop_self_loops": True},
        "rows_scanned": seen,
        "added_per_relation": dict(per_rel_added.most_common()),
        "duplicates_per_relation": dict(per_rel_dup),
        "dropped_hangul": dropped_hangul,
        "dropped_filters": dropped_filters,
        "total_edges": len(store),
        "elapsed_s": round(time.time() - t0, 1),
    }
    (STAGING / "R2v2_STAGING_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
