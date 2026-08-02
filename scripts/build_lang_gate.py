# -*- coding: utf-8 -*-
"""Build lang_gate.col — the English-only containment sidecar.

OWNER DIRECTIVE (2026-07-17): " 
 " — Korean must never surface in extraction or answers. Minimal-complete
containment, not maximal deletion.

WHY A SIDECAR AGAIN
 The store holds millions of rows touching Hangul (crocodile defined_as , is_a
 , dictionary defined_as ). Under the English-core doctrine none of them may ever
 surface, but deleting them violates no-reset and burns real knowledge (the KO→EN DBpedia
 mappings are 98% sourced). The verdict sidecar already proved the mechanism: one uint8 per
 row, readers skip flagged rows, delete the file and behavior fully reverts. This applies the
 same mechanism to LANGUAGE instead of evidence:

 gate 0 = row is Hangul-free -> readable
 gate 1 = subject or object has Hangul -> skipped by every store read

 Gating at the store read API is the single-exit-gate doctrine applied to READS: this session
 alone found four separate lanes each doing (or forgetting) their own Hangul filtering —
 lexicon glosses, engage, composers, the chat exit. One gate under all of them ends the class.

WHAT THIS DOES NOT DO
 * It does not judge evidence — that stays isa_verdict.col's job. The two compose.
 * It does not delete: is_a stays on disk, verdict-kept, language-hidden.
 * It does not touch the Korean raw dumps (kaikki-ko etc.) — sources, not store rows.

USAGE
 python scripts/build_lang_gate.py # build (atomic replace; engine may run)
 python scripts/build_lang_gate.py --stats # report only, write nothing
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_HAN = re.compile(r"[가-힣]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="measure only, write nothing")
    ap.add_argument(
        "--store-root",
        help=(
            "existing canonical sibling candidate "
            "kg_triples.staged_merge.<id>; required for writes"
        ),
    )
    args = ap.parse_args()

    if args.store_root:
        import scripts.landing_chain_lib as landing_chain
        from packages.graph_scale.triple_store import TripleStore

        candidate = landing_chain._validate_candidate_lane(
            landing_chain.CANONICAL_SHIPPED_ROOT,
            args.store_root,
            require_exists=True,
        )
        st = TripleStore(candidate)
    elif args.stats:
        from packages.graph_scale.lexicon_lane import _store

        st = _store()
    else:
        ap.error(
            "--store-root is required for builds; canonical shipped data is "
            "read-only"
        )

    # Sidecar construction bypasses the ordinary column API. Statistics are
    # read-only; every write is confined to the canonical sibling candidate.
    if not args.stats:
        st._require_writable("language-gate sidecar build")
    root = st.root
    S = np.memmap(root / "s.col", dtype=np.int32, mode="r")
    O = np.memmap(root / "o.col", dtype=np.int32, mode="r")
    n = len(S)
    print(f"rows={n}")

    # resolve each unique term id -> has-Hangul once; the row pass is then two dict hits
    t0 = time.time()
    uids = np.unique(np.concatenate([np.unique(S), np.unique(O)]))
    han: dict[int, bool] = {}
    for i, g in enumerate(uids):
        term = st.terms.term(int(g))
        han[int(g)] = bool(term and _HAN.search(term))
        if i and i % 1000000 == 0:
            print(f"  terms {i}/{len(uids)}  {time.time()-t0:.0f}s")
    n_han_terms = sum(1 for v in han.values() if v)
    print(f"terms resolved: {len(uids)} uniques, {n_han_terms} contain Hangul "
          f"({time.time()-t0:.0f}s)")

    t0 = time.time()
    gate = np.zeros(n, dtype=np.uint8)
    for j in range(n):
        if han[int(S[j])] or han[int(O[j])]:
            gate[j] = 1
        if j and j % 5000000 == 0:
            print(f"  rows {j}/{n}  {time.time()-t0:.0f}s")
    flagged = int(gate.sum())
    print(f"rows touching Hangul: {flagged} ({100*flagged/n:.1f}%)  ({time.time()-t0:.0f}s)")

    if args.stats:
        print("--stats: nothing written")
        return 0

    tmp = root / "lang_gate.col.tmp"
    gate.tofile(tmp)
    out = root / "lang_gate.col"
    os.replace(tmp, out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
