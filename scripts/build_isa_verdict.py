# -*- coding: utf-8 -*-
"""Build isa_verdict.col — the evidence annotation that quarantines unsourced is_a rows.

WHAT WAS MEASURED (2026-07-17)
 kg_triples holds 26.9M rows; 19.6M are src=0 is_a. Of the EN-EN ones, only 112,928 are
 asserted by a source that exists on disk (ConceptNet 5.7 IsA: 221,566 pairs; Kaikki-en
 structured hypernyms: 28,042 pairs). 17,147,951 are asserted by NOTHING — and a 3,000-row
 sample shows 98% are not derivable from the evidenced base within 3 hops either. The failure
 shape is systematic ('adobe lily is_a housing' = the hypernym of 'adobe'; crocodile carries
 388 parents of which ~4 are real): a buggy bulk write, not knowledge.

WHY A SIDECAR AND NOT DELETION
 * tombstones: mechanically impossible at 17M (the jsonl loads as a RAM set per reader).
 * rebuild: violates the no-reset doctrine (store restarts are operator-only).
 * sidecar: one uint8 per row. Rows never move, nothing is deleted, and removing
 isa_verdict.col reverts the store to byte-identical behavior. This is 
 enforced retroactively: a row nobody asserted does not get to answer questions.

V3 — KOREAN ROWS: JUDGED BY DIRECTION (2026-07-17, measured)
 Full judgment of Hangul rows stays blocked (KO whitelist covers real KO→KO taxonomy poorly:
 →, → are asserted by nothing on disk). But splitting the 60k-row sample
 BY DIRECTION separates the bug from the knowledge perfectly:
 EN→KO coverage 0/6555 — every row is the bulk-write bug ('eosin is_a ',
 'iron lung is_a '). NOTHING legitimate asserts is_a in this direction.
 KO→EN coverage 98% (DBpedia-ko instance-types: ' is_a Beverage') — kept, unjudged.
 KO→KO tiny (0.05%), whitelist incomplete for it — kept, unjudged (→ lives
 here; quarantining on 0% coverage would repeat the failed-sweep trap).
 So v3 quarantines ONLY unsourced EN→KO rows (~11% of src=0 is_a ≈ 2.1M). Honest side note:
 real translation edges like 'crocodile is_a ' fall in this direction and are quarantined
 too — correctly, because a translation is an ALIAS, not a taxonomy parent, and the alias lane
 already holds these pairs (DBpedia labels wrote them symmetrically).
 KO whitelist v2 = wikidata_ko/wikipedia_ko ledgers (94,185) + DBpedia-ko instance-types
 (253,051) + ConceptNet ko-involved (430); kaikki-ko hypernyms = ZERO (field unused in the
 KO edition).

VERDICTS
 1 = keep: source-asserted (ConceptNet ∪ Kaikki), OR out of scope (non-is_a rows, src≠0 rows,
 any row touching Hangul — the Korean lane is measured-good and is not judged here).
 2 = keep: not asserted directly but derivable ≤3 hops from the evidenced base (transitive
 closure is legitimate; only ~2% of unsourced rows qualify, measured).
 0 = quarantine: asserted by nothing, derivable from nothing. Readers skip these.

USAGE
 python scripts/build_isa_verdict.py --pairs-dir <dir with cn_isa_pairs.pkl / kaikki_isa_pairs.pkl>
 (re-extract the pickles with the one-liners in the commit message if the scratchpad is gone)
"""
from __future__ import annotations

import argparse
import pickle
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_HAN = re.compile(r"[가-힣]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-dir", required=True)
    ap.add_argument(
        "--store-root",
        required=True,
        help=(
            "existing canonical sibling candidate "
            "kg_triples.staged_merge.<id>"
        ),
    )
    ap.add_argument("--max-hops", type=int, default=3)
    args = ap.parse_args()

    import scripts.landing_chain_lib as landing_chain
    from packages.graph_scale.triple_store import TripleStore

    candidate = landing_chain._validate_candidate_lane(
        landing_chain.CANONICAL_SHIPPED_ROOT,
        args.store_root,
        require_exists=True,
    )
    st = TripleStore(candidate)
    # This script writes a raw sidecar with numpy/os.replace, so enforce the
    # substrate authority boundary before performing its expensive scan. The
    # candidate is later sealed and promoted by the signed swap boundary.
    st._require_writable("is-a verdict sidecar build")
    root = st.root
    S = np.memmap(root / "s.col", dtype=np.int32, mode="r")
    P = np.memmap(root / "p.col", dtype=np.int32, mode="r")
    O = np.memmap(root / "o.col", dtype=np.int32, mode="r")
    SRC = np.memmap(root / "src.col", dtype=np.int32, mode="r")
    n = len(S)
    isa = st.terms.lookup("is_a")

    pairs_dir = Path(args.pairs_dir)
    C = pickle.load(open(pairs_dir / "cn_isa_pairs.pkl", "rb"))
    K = pickle.load(open(pairs_dir / "kaikki_isa_pairs.pkl", "rb"))
    W = C | K
    ko_path = pairs_dir / "ko_isa_pairs_v2.pkl"
    KOW = pickle.load(open(ko_path, "rb")) if ko_path.exists() else set()
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in W:
        adj[a].add(b)
    print(f"rows={n}  whitelist={len(W)}")

    verdict = np.ones(n, dtype=np.uint8)          # default keep (out of scope)
    scope = (P == isa) & (SRC == 0)
    rows = np.where(scope)[0]
    print(f"scope rows (is_a & src=0): {len(rows)}")

    # resolve unique terms once — 7.25M uniques measured ≈ 156s
    t0 = time.time()
    uids = np.unique(np.concatenate([S[rows], O[rows]]))
    term: dict[int, str] = {}
    for i, g in enumerate(uids):
        term[int(g)] = st.terms.term(int(g))
        if i % 500000 == 0 and i:
            print(f"  terms {i}/{len(uids)}  {time.time()-t0:.0f}s")
    print(f"terms resolved {time.time()-t0:.0f}s")

    memo: dict[str, set[str]] = {}

    def reach(src_word: str) -> set[str]:
        """Everything reachable from src_word in ≤max_hops over the evidenced base."""
        hit = memo.get(src_word)
        if hit is not None:
            return hit
        seen: set[str] = set()
        frontier = {src_word}
        for _ in range(args.max_hops):
            nxt: set[str] = set()
            for x in frontier:
                for y in adj.get(x, ()):  # most words miss instantly — adj is tiny
                    if y not in seen:
                        seen.add(y)
                        nxt.add(y)
            frontier = nxt
            if not frontier:
                break
        memo[src_word] = seen
        return seen

    t0 = time.time()
    kept_src = kept_der = quarantined = ko_skip = 0
    for j, r in enumerate(rows):
        s = term[int(S[r])]
        o = term[int(O[r])]
        hs, ho = bool(_HAN.search(s)), bool(_HAN.search(o))
        if hs or ho:
            # V3: only the EN→KO direction is judged — measured 0/6555 sourced, all bug.
            # KO→KO and KO→EN keep verdict 1 (evidence incomplete / 98% covered respectively).
            if (not hs) and ho and (s.lower(), o.lower()) not in KOW:
                verdict[r] = 0
                quarantined += 1
            else:
                ko_skip += 1
            continue
        sl, ol = s.lower(), o.lower()
        if (sl, ol) in W:
            kept_src += 1
        elif ol in reach(sl):
            verdict[r] = 2
            kept_der += 1
        else:
            verdict[r] = 0
            quarantined += 1
        if j % 2000000 == 0 and j:
            print(f"  verdict {j}/{len(rows)}  {time.time()-t0:.0f}s")

    # atomic-ish: never let a reader lazily open a half-written sidecar
    import os
    tmp = root / "isa_verdict.col.tmp"
    verdict.tofile(tmp)
    out = root / "isa_verdict.col"
    os.replace(tmp, out)
    print(f"\n=== sourced {kept_src} | derivable {kept_der} | QUARANTINED {quarantined} | "
          f"ko-untouched {ko_skip}")
    print(f"wrote {out} ({out.stat().st_size} bytes) in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
