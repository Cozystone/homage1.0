# -*- coding: utf-8 -*-
"""Plan B / B2 supervision miner — turn the curated knowledge graph into (mention, neighborhood) text
pairs for graph-grounded contrastive pretraining. Positive pair = an entity's surface form and the
verbalisation of its 1-hop graph neighborhood. This is the unique ATANOR lever: meaning as *position
relative to the graph*, supervised for free by every edge we already hold — No-LLM, sourced, zero
fabrication (each object is a stored fact). Output: data/graph_scale/graph_pairs.jsonl

  python scripts/ace2_mine_graph_pairs.py [n_pairs] [min_facts]

Read-only against the live store (write_src=False); safe to run anytime. Consumed by
scripts/ace2_pretrain_multitask.py (B2). If this file is absent, the trainer simply skips B2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT     # noqa: E402
from packages.graph_scale.triple_store import TripleStore           # noqa: E402

OUT = REPO / "data" / "graph_scale" / "graph_pairs.jsonl"


def main() -> int:
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
    min_facts = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    store = TripleStore(
        SHIPPED_GRAPH_ROOT,
        dict_backend="ram",
        write_src=False,
    )
    cols = store.open_columns()
    s_col = cols["s"]
    n_rows = len(s_col)
    if n_rows == 0:
        print("store empty — no pairs mined", flush=True)
        return 1
    rng = np.random.default_rng(0)
    # sample rows (a subject can own many rows); dedup subjects, verbalise each neighborhood once
    order = rng.permutation(n_rows)
    seen: set[str] = set()
    written = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        for ridx in order:
            if written >= n_pairs:
                break
            sid = int(s_col[int(ridx)])
            subj = store.terms.term(sid)
            if not subj or subj in seen:
                continue
            seen.add(subj)
            facts = store.facts_about(subj, limit=8)
            if len(facts) < min_facts:
                continue
            # verbalise the neighborhood: "subject: pred obj; pred obj; ..."  (grounded, sourced facts)
            neigh = "; ".join(f"{p} {o}" for (_s, p, o) in facts)
            fh.write(json.dumps({"mention": subj, "neighborhood": f"{subj}: {neigh}"},
                                ensure_ascii=False) + "\n")
            written += 1
            if written % 20_000 == 0:
                print(f"  {written:,} pairs…", flush=True)
    print(f"RESULT graph_pairs {json.dumps({'written': written, 'out': OUT.name, 'unique_subjects': len(seen)})}",
          flush=True)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
