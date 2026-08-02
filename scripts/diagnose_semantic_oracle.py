# -*- coding: utf-8 -*-
"""E9 verdict — can the TRAINED semantic scorer clear the ceilings the lexical family could not?

FROZEN BEFORE THE MODEL EXISTS (2026-07-18, pre-registration): this script, its thresholds and
its slice (slice_25_fresh.jsonl, sha256 849ea917…, zero overlap with the diagnostic slice) were
committed before RTD pretraining started, so the verdict cannot be shaped by peeking.

Two pre-declared gates (docs/ATANOR_four_walls_research.md E9-(v) / E10):
  ORACLE    gold-uniquely-best under the semantic scorer >= 0.30   (lexical family: 0.105-0.165)
  D1-SEM    margin-elimination with the semantic scorer: fired >= 0.25, gold_kill <= 0.08,
            survivor-pick exp acc >= 0.30                          (symbolic detector: triple red)

Scorer: fine-tuned ACE2 (ace2_squad.pt) answerability head — score(option, sentence) =
P(answerable | q=option, ctx=sentence); an option's score = max over retrieved sentences.
Retrieval protocol IDENTICAL to the lexical diagnostics (title match + disk BM25 top-3) so the
only changed variable is the scorer. Margin elimination: eliminate options scoring below
(top - MARGIN) when the top option is confidently supported (top >= TAU).

Usage:  python scripts/diagnose_semantic_oracle.py [slice.jsonl] [--ckpt path]
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_SLICE = REPO / "data" / "benchmarks" / "mmlu" / "slice_25_fresh.jsonl"
EN_PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
CKPT = REPO / "data" / "graph_scale" / "ace2_squad.pt"
TAU = 0.55        # top option must be confidently supported before anything is eliminated
MARGIN = 0.25     # options more than this below the top are eliminated


def main() -> int:
    import torch
    from packages.reasoning_vm.ace import data2 as D2
    from packages.reasoning_vm.ace.model2 import Ace2Encoder
    from packages.reasoning_vm.openbook import _SENT, load_disk_index, load_passages, retrieve

    t0 = time.time()
    ckpt = Path(sys.argv[sys.argv.index("--ckpt") + 1]) if "--ckpt" in sys.argv else CKPT
    skip = {str(ckpt)} if "--ckpt" in sys.argv else set()
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in skip]
    path = Path(args[0]) if args else DEFAULT_SLICE
    if not ckpt.exists():
        print(f"checkpoint missing: {ckpt} — run Phase C first")
        return 1
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = D2.tokenizer()
    model = Ace2Encoder(tok.get_vocab_size()).to(dev).eval()
    model.load_state_dict(torch.load(ckpt, map_location=dev), strict=False)
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    passages = load_passages(str(EN_PASSAGES))
    di = load_disk_index()
    print(f"slice={path.name} n={len(rows)} ckpt={ckpt.name} dev={dev}")

    def score_pairs(pairs: list[tuple[str, str]]) -> np.ndarray:
        out = []
        for i in range(0, len(pairs), 64):
            chunk = pairs[i:i + 64]
            b = D2.collate([D2.encode(q, c) for q, c in chunk], tok)
            b = {k: v.to(dev) for k, v in b.items()}
            with torch.no_grad(), torch.autocast(dev, dtype=torch.bfloat16, enabled=(dev == "cuda")):
                ans, _s, _e = model(b["ids"], b["seg"], b["feats"], b["pad"])
            out.append(torch.sigmoid(ans.float()).cpu().numpy())
        return np.concatenate(out, 0) if out else np.zeros(0)

    n = len(rows)
    oracle = fired = gold_kill = 0
    surv_prob, surv_n = 0.0, 0
    scored_items = 0
    for r in rows:
        stem, ch, gold = r["question"], r["choices"], r["gold"]
        texts = []
        got = retrieve(stem, passages, None)
        if got:
            texts.append(got[1])
        if di is not None:
            texts.extend(t for _ti, t in di.search_topk(stem, k=3))
        sents = [s for t in texts for s in _SENT.split(t) if len(s.strip()) >= 20][:60]
        if not sents:
            continue
        scored_items += 1
        keys = list(ch)
        pairs = [(ch[k], s) for k in keys for s in sents]
        sc = score_pairs(pairs).reshape(len(keys), len(sents)).max(axis=1)
        top = float(sc.max())
        # oracle: gold uniquely best under the semantic scorer
        if ch.get(gold) is not None:
            gi = keys.index(gold)
            if sc[gi] == top and (sc == top).sum() == 1:
                oracle += 1
        # margin elimination
        if top >= TAU:
            elim = [k for k, v in zip(keys, sc) if v < top - MARGIN]
            if elim:
                fired += 1
                if gold in elim:
                    gold_kill += 1
                survivors = [k for k in keys if k not in elim]
                surv_n += 1
                surv_prob += (1.0 / len(survivors)) if gold in survivors else 0.0

    print(f"\nscored items                 : {scored_items}/{n}")
    print(f"ORACLE gold-uniquely-best    : {oracle / n:.4f}   [lexical 0.105-0.165; gate >=0.30]")
    print(f"D1-SEM fired                 : {fired / n:.3f}   [gate >=0.25]")
    if fired:
        print(f"D1-SEM gold_kill             : {gold_kill / fired:.3f}   [gate <=0.08]")
    if surv_n:
        print(f"D1-SEM survivor exp acc      : {surv_prob / surv_n:.3f}   [gate >=0.30]")
    print(f"elapsed {round(time.time() - t0, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
