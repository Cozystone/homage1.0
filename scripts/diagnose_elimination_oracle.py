# -*- coding: utf-8 -*-
"""E10-D1 — elimination-channel diagnostic, run BEFORE any cascade wiring (oracle-first rule).

Measures, on MMLU-200 with the SAME retrieval the cascade would see:
  fired      fraction of items where >=1 option got eliminated
  gold_kill  fraction of FIRED items where the eliminated set includes GOLD  <- the poison metric
  exp_acc    expected accuracy of a uniform pick among survivors on fired items
             (baseline 0.25; elimination that only kills distractors raises it)
  neg_pick   negated-stem items where the single contradicted option IS gold (direct wins)

Pre-declared gates (recorded in docs/ATANOR_four_walls_research.md E10 BEFORE this ran):
  gold_kill <= 0.08 · fired >= 0.25 · exp_acc >= 0.30.
Usage: python scripts/diagnose_elimination_oracle.py [slice.jsonl] [--pool N]
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from packages.reasoning_vm.concept_filter import (apply_verdicts, eliminate,  # noqa: E402
                                                  stem_is_negated)
from packages.reasoning_vm.openbook import load_disk_index, load_passages, retrieve  # noqa: E402

DEFAULT_SLICE = REPO / "data" / "benchmarks" / "mmlu" / "slice_25.jsonl"
EN_PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"


def main() -> int:
    pool = int(sys.argv[sys.argv.index("--pool") + 1]) if "--pool" in sys.argv else 3
    skip = {sys.argv[sys.argv.index("--pool") + 1]} if "--pool" in sys.argv else set()
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in skip]
    path = Path(args[0]) if args else DEFAULT_SLICE
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    passages = load_passages(str(EN_PASSAGES))
    di = load_disk_index()
    print(f"slice={path.name} n={len(rows)} passages={len(passages)} disk_index={bool(di)} pool={pool}")

    n = len(rows)
    fired = gold_kill = neg_items = neg_gold_pick = 0
    surv_prob_sum, surv_items = 0.0, 0
    pick_right = pick_total = 0
    for r in rows:
        stem, ch, gold = r["question"], r["choices"], r["gold"]
        texts: list[str] = []
        got = retrieve(stem, passages, None)           # title-match (cascade parity)
        if got:
            texts.append(got[1])
        if di is not None:                             # + BM25 pool (the coverage the cascade adds)
            texts.extend(t for _ti, t in di.search_topk(stem, k=pool))
        verd = eliminate(stem, ch, texts)
        elim = [k for k, v in verd.items() if v.eliminated]
        if not elim:
            continue
        fired += 1
        if stem_is_negated(stem):
            neg_items += 1
            act = apply_verdicts(stem, ch, verd)
            if act.get("action") == "pick":
                pick_total += 1
                if act["choice_key"] == gold:
                    neg_gold_pick += 1
                    pick_right += 1
            continue
        if gold in elim:
            gold_kill += 1
        survivors = [k for k in ch if k not in elim]
        if survivors:
            surv_items += 1
            surv_prob_sum += (1.0 / len(survivors)) if gold in survivors else 0.0
        act = apply_verdicts(stem, ch, verd)
        if act.get("action") == "pick":
            pick_total += 1
            pick_right += int(act["choice_key"] == gold)

    print(f"\nfired items                     : {fired}/{n} = {fired / n:.3f}   [gate >=0.25]")
    if fired:
        print(f"gold killed (of fired, non-neg) : {gold_kill}/{max(1, fired - neg_items)} = "
              f"{gold_kill / max(1, fired - neg_items):.3f}   [gate <=0.08]")
    if surv_items:
        print(f"exp acc among survivors         : {surv_prob_sum / surv_items:.3f}   "
              f"[baseline 0.25, gate >=0.30]")
    print(f"negated-stem direct picks       : {pick_right}/{pick_total} correct "
          f"(of {neg_items} fired negated items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
