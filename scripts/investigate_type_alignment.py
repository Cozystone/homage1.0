#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-ONLY investigation: cross-source type-vocabulary alignment candidates.

Different sources label the SAME type differently — DBpedia says 'Settlement',
'City'; the Korean sources say '', ''. When both labels land as is_a
parents of the SAME entities, that co-occurrence is evidence they name one type.
This script measures that co-occurrence over the live graph and writes a ranked
candidate TSV. It NEVER writes to the store — the output is a report a human (or
a Fable pass) reviews before any alias edge is promoted.

Guarded (same measured discriminator as the derivation lane): subjects with more
than --max-degree is_a parents are noise magnets (jigsaw is_a <1315 things>) and
are skipped, or their spurious co-occurrences would dominate.

 python scripts/investigate_type_alignment.py --top 200 --min-count 3
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _d in sorted(glob.glob(str(ROOT / "packages" / "*"))):
    if os.path.isdir(_d):
        sys.path.append(_d)


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)


def _script_class(a: str, b: str) -> str:
    ha, hb = _has_hangul(a), _has_hangul(b)
    if ha and hb:
        return "ko-ko"
    if ha != hb:
        return "ko-en"      # the cross-vocabulary bridge we most want
    return "en-en"          # City ↔ Settlement etc.


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=200)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--max-degree", type=int, default=8, help="skip is_a noise magnets")
    ap.add_argument("--out", default=str(ROOT / "data" / "graph_scale" / "type_alignment_candidates.tsv"))
    args = ap.parse_args()

    from packages.graph_scale import answer_bridge as ab

    st = ab._store()
    if st is None:
        raise SystemExit("store unavailable")
    root = st.root
    s = np.fromfile(root / "s.col", dtype="<i4")
    p = np.fromfile(root / "p.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    n = min(len(s), len(p), len(o))
    s, p, o = s[:n], p[:n], o[:n]
    pid = st.terms.lookup("is_a")
    if pid is None:
        raise SystemExit("no is_a predicate")
    m = p == pid
    ss, oo = s[m], o[m]
    print(f"is_a edges: {int(m.sum()):,}", file=sys.stderr)

    # label frequency: how many DISTINCT subjects carry each is_a parent — the


    # with the same parent twice must count once.
    subj_parent = np.unique(np.stack([ss, oo], axis=1), axis=0)
    label_freq: Counter = Counter(int(x) for x in subj_parent[:, 1])

    # group parents by subject (sort by subject -> contiguous runs)
    order = np.argsort(ss, kind="stable")
    ss, oo = ss[order], oo[order]
    uniq, first = np.unique(ss, return_index=True)
    last = np.append(first[1:], len(ss))

    pair_count: Counter = Counter()
    pair_examples: dict[tuple[int, int], list[int]] = defaultdict(list)
    skipped_magnets = 0
    term = st.terms.term
    for i in range(len(uniq)):
        lo, hi = int(first[i]), int(last[i])
        parents = np.unique(oo[lo:hi])
        if len(parents) < 2:
            continue
        if len(parents) > args.max_degree:
            skipped_magnets += 1
            continue
        subj = int(uniq[i])
        for a, b in combinations(sorted(int(x) for x in parents), 2):
            key = (a, b)
            pair_count[key] += 1
            if len(pair_examples[key]) < 3:
                pair_examples[key].append(subj)

    print(f"distinct co-occurring parent pairs: {len(pair_count):,} "
          f"(skipped {skipped_magnets:,} noise-magnet subjects)", file=sys.stderr)

    rows = []
    for (a, b), c in pair_count.items():
        if c < args.min_count:
            continue
        la, lb = term(a), term(b)
        if not la or not lb or la == lb:
            continue
        fa, fb = label_freq[a], label_freq[b]
        # containment: fraction of the narrower/broader label's subjects shared.
        # SYNONYM => both high; HYPONYM => the child's containment is high while
        # the broad parent's is low; NOISE => both low (accidental overlap).
        cont_a = c / max(fa, 1)   # of a's subjects, how many also have b
        cont_b = c / max(fb, 1)
        lo, hi = sorted((cont_a, cont_b))
        if hi >= 0.6 and lo >= 0.5:
            verdict = "synonym"       # alignable as alias (a == b)
        elif hi >= 0.6 and lo < 0.25:
            verdict = "hyponym"       # already an is_a; DO NOT alias
        else:
            verdict = "review"
        cls = _script_class(la, lb)
        ex = ", ".join(term(x)[:20] for x in pair_examples[(a, b)])
        rows.append((c, cls, verdict, la, lb, fa, fb, round(cont_a, 2), round(cont_b, 2), ex))

    # ko-en synonyms first (the actionable bridges), then by count
    _cls_rank = {"ko-en": 0, "ko-ko": 1, "en-en": 2}
    _v_rank = {"synonym": 0, "review": 1, "hyponym": 2}
    rows.sort(key=lambda r: (_cls_rank.get(r[1], 9), _v_rank.get(r[2], 9), -r[0]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("cooccur\tscript\tverdict\tlabel_a\tlabel_b\tfreq_a\tfreq_b\tcont_a\tcont_b\texample_subjects\n")
        for c, cls, v, la, lb, fa, fb, ca, cb, ex in rows[: args.top]:
            fh.write(f"{c}\t{cls}\t{v}\t{la}\t{lb}\t{fa}\t{fb}\t{ca}\t{cb}\t{ex}\n")

    from collections import Counter as _C
    cls_dist = _C(r[1] for r in rows)
    koen_v = _C(r[2] for r in rows if r[1] == "ko-en")
    print(f"\nwrote {min(len(rows), args.top):,} of {len(rows):,} candidates -> {out}", file=sys.stderr)
    print(f"by script (>= min-count): {dict(cls_dist)}", file=sys.stderr)
    print(f"ko-en verdicts: {dict(koen_v)}", file=sys.stderr)

    # DISJOINT-VOCABULARY DIAGNOSTIC: the load-bearing finding. If two labels
    # name the same type they should have similar frequency AND high overlap.
    # Report same-frequency ko-en pairs whose overlap is near-zero — that is the
    # fingerprint of two vocabularies partitioning DIFFERENT entity sets, which

    # overlap 10 -> containment 0.00).
    print("\nDISJOINT-SET fingerprint (same-freq ko-en pairs, near-zero overlap):", file=sys.stderr)
    for c, cls, v, la, lb, fa, fb, ca, cb, ex in rows:
        if cls == "ko-en" and min(fa, fb) >= 100 and max(ca, cb) < 0.05:
            ratio = min(fa, fb) / max(fa, fb, 1)
            print(f"  {la}({fa:,}) ~ {lb}({fb:,})  freq-ratio {ratio:.2f}, overlap {c} "
                  f"-> containment {ca}/{cb}", file=sys.stderr)


if __name__ == "__main__":
    main()
