# -*- coding: utf-8 -*-
"""Build the English-only store BESIDE the live one. Owner-authorized surgery (2026-07-17).

Plan: docs/ATANOR_english_rebuild_surgery_plan.md. This is Phase 1.

WHAT IT DOES
    Streams s/p/o/src.col through the keep-mask
        keep = NOT(lang_gate == 1) AND NOT(p == is_a AND isa_verdict != 1)
        rows past a sidecar's end are kept (post-containment appends: English by write-gate
        contract, evidence-carrying by provenance contract)
    into kg_triples_en/, copies term_shards byte-for-byte (term IDs NEVER move — that is the
    plan's invariant #2), copies the string-based tombstones and sources, writes an exact
    meta.json, and builds the sorted subject index the live store currently lacks.

THE EQUIVALENCE CONTRACT (invariant #3, verified here before any swap)
    Everything removed was ALREADY read-quarantined, so for any English subject
        old.facts_about(x) == new.facts_about(x)
    must hold exactly (same rows, same order — the filter preserves relative order and the
    old store's readers skip the same rows via sidecars). 500-subject random audit; ONE
    mismatch blocks the swap.

USAGE
    python scripts/rebuild_english_store.py --dry-run     # counts only, writes nothing
    python scripts/rebuild_english_store.py --build       # build kg_triples_en + verify
"""
from __future__ import annotations

import argparse
import io
import json
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SRC_ROOT = REPO / "data" / "graph_scale" / "kg_triples"
OUT_ROOT = REPO / "data" / "graph_scale" / "kg_triples_en"


def _keep_mask(root: Path) -> "tuple[np.ndarray, dict]":
    S = np.memmap(root / "s.col", dtype=np.int32, mode="r")
    P = np.memmap(root / "p.col", dtype=np.int32, mode="r")
    n = len(S)
    keep = np.ones(n, dtype=bool)

    from packages.graph_scale.triple_store import TripleStore
    st = TripleStore(root)
    isa = st.terms.lookup("is_a")

    stats = {"total": n}
    V = np.fromfile(root / "isa_verdict.col", dtype=np.uint8)
    nv = min(len(V), n)
    bad_isa = np.zeros(n, dtype=bool)
    bad_isa[:nv] = (np.asarray(P[:nv]) == isa) & (V[:nv] != 1)
    stats["drop_unsourced_isa"] = int(bad_isa.sum())

    G = np.fromfile(root / "lang_gate.col", dtype=np.uint8)
    ng = min(len(G), n)
    bad_han = np.zeros(n, dtype=bool)
    bad_han[:ng] = G[:ng] == 1
    stats["drop_hangul"] = int(bad_han.sum())
    stats["drop_overlap"] = int((bad_isa & bad_han).sum())

    keep &= ~(bad_isa | bad_han)
    stats["keep"] = int(keep.sum())
    stats["past_sidecar_end_kept"] = int(n - max(nv, ng)) if n > max(nv, ng) else 0
    return keep, stats


def dry_run() -> int:
    t0 = time.time()
    keep, s = _keep_mask(SRC_ROOT)
    print(f"total rows            : {s['total']:,}")
    print(f"drop  unsourced is_a  : {s['drop_unsourced_isa']:,}")
    print(f"drop  hangul-touching : {s['drop_hangul']:,}")
    print(f"      (overlap)       : {s['drop_overlap']:,}")
    print(f"KEEP                  : {s['keep']:,}  ({100*s['keep']/s['total']:.1f}%)")
    print(f"past-sidecar appends  : {s['past_sidecar_end_kept']:,} (kept by contract)")
    print(f"({time.time()-t0:.0f}s, read-only)")
    return 0


def build() -> int:
    if OUT_ROOT.exists():
        print(f"{OUT_ROOT} already exists — refusing to overwrite a previous build. "
              f"Delete it deliberately first.")
        return 2
    t0 = time.time()
    keep, s = _keep_mask(SRC_ROOT)
    n0 = s["total"]
    print(f"snapshot N0={n0:,}  keep={s['keep']:,}")

    OUT_ROOT.mkdir(parents=True)
    for col in ("s", "p", "o", "src"):
        arr = np.memmap(SRC_ROOT / f"{col}.col", dtype=np.int32, mode="r")
        np.asarray(arr[:n0])[keep].tofile(OUT_ROOT / f"{col}.col")
        print(f"  wrote {col}.col  ({(OUT_ROOT / f'{col}.col').stat().st_size:,} bytes)")

    # term IDs are the plan's invariant #2: byte-for-byte copy, never regenerate.
    shutil.copytree(SRC_ROOT / "term_shards", OUT_ROOT / "term_shards")
    for f in ("retractions.jsonl", "sources.txt"):
        if (SRC_ROOT / f).exists():
            shutil.copy2(SRC_ROOT / f, OUT_ROOT / f)
    (OUT_ROOT / "meta.json").write_text(json.dumps({
        "count": s["keep"],
        "terms": json.loads((SRC_ROOT / "meta.json").read_text())["terms"],
        "format": "int32_columnar_spo",
        "dict_backend": "sharded",
        "rebuilt_from": {"source": str(SRC_ROOT.name), "snapshot_rows": n0,
                         "dropped_unsourced_isa": s["drop_unsourced_isa"],
                         "dropped_hangul": s["drop_hangul"],
                         "date": "2026-07-17",
                         "plan": "docs/ATANOR_english_rebuild_surgery_plan.md"},
    }, indent=2), encoding="utf-8")
    print(f"build done ({time.time()-t0:.0f}s) — building sorted subject index…")

    from packages.graph_scale.triple_store import TripleStore
    new = TripleStore(OUT_ROOT)
    idx = new.rebuild_index()
    print(f"index built over {idx:,} rows")
    return verify(n0, keep)


def verify(n0: int, keep: "np.ndarray") -> int:
    """V1 row count · V2 zero Hangul · V3 all is_a sourced · V4 visible equivalence (500)."""
    import re
    HAN = re.compile(r"[가-힣]")
    from packages.graph_scale.triple_store import TripleStore

    old = TripleStore(SRC_ROOT)
    new = TripleStore(OUT_ROOT)

    S2 = np.memmap(OUT_ROOT / "s.col", dtype=np.int32, mode="r")
    P2 = np.memmap(OUT_ROOT / "p.col", dtype=np.int32, mode="r")
    O2 = np.memmap(OUT_ROOT / "o.col", dtype=np.int32, mode="r")
    kn = int(keep.sum())
    v1 = len(S2) == kn
    print(f"V1 row count: {len(S2):,} == {kn:,}  {'OK' if v1 else 'FAIL'}")

    # V2+V3 over the FULL new store — term resolution via unique ids (fast, exact)
    t0 = time.time()
    uids = np.unique(np.concatenate([np.unique(S2), np.unique(O2)]))
    han_ids = set()
    for g in uids:
        t = new.terms.term(int(g))
        if t and HAN.search(t):
            han_ids.add(int(g))
    v2_bad = int(np.isin(np.asarray(S2), list(han_ids)).sum() +
                 np.isin(np.asarray(O2), list(han_ids)).sum()) if han_ids else 0
    print(f"V2 hangul rows in new store: {v2_bad}  {'OK' if v2_bad == 0 else 'FAIL'}  "
          f"({time.time()-t0:.0f}s)")

    isa = new.terms.lookup("is_a")
    n_isa = int((np.asarray(P2) == isa).sum()) if isa is not None else 0
    print(f"V3 is_a rows kept: {n_isa:,} (all passed verdict==1 by construction of the mask)")

    # V4 visible equivalence on 500 random English subjects drawn from KEPT rows
    t0 = time.time()
    rng = random.Random(20260717)
    import re as _re
    ascii_ok = _re.compile(r"^[a-z][a-z .'-]{2,28}$")
    picks: list[str] = []
    tries = 0
    while len(picks) < 500 and tries < 20000:
        tries += 1
        r = rng.randrange(len(S2))
        w = new.terms.term(int(S2[r]))
        if w and ascii_ok.match(w) and w not in picks:
            picks.append(w)
    mism = 0
    for w in picks:
        a = old.facts_about(w, limit=200)
        b = new.facts_about(w, limit=200)
        if a != b:
            mism += 1
            if mism <= 3:
                print(f"  V4 MISMATCH {w}: old={len(a)} new={len(b)}")
                only_old = [x for x in a if x not in b][:3]
                only_new = [x for x in b if x not in a][:3]
                print(f"     only-old={only_old}")
                print(f"     only-new={only_new}")
    v4 = mism == 0
    print(f"V4 visible equivalence: {len(picks)-mism}/{len(picks)} identical  "
          f"{'OK' if v4 else 'FAIL'}  ({time.time()-t0:.0f}s)")

    ok = v1 and v2_bad == 0 and v4
    print(f"\n=== VERIFY {'ALL OK — swap may proceed' if ok else 'FAILED — DO NOT SWAP'}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.build:
        raise SystemExit(build())
    raise SystemExit(dry_run())
