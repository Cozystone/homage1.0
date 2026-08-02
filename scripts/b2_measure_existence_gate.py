# -*- coding: utf-8 -*-
"""Tier B / B2 lever i — the EXISTENCE gate: is the gold-option's DISTINCTIVE evidence PRESENT in the
retrieved passage? Measured lead-corpus baseline on slice_25_fresh = 0.145 (consistent with the E6b
0.105-0.165 ceiling); the pre-declared lever-i gate is body-corpus presence >= 0.60 (a clear
majority = the evidence is actually there to retrieve).

This is the fail-fast decision for lever i, measured BEFORE any semantic scorer: if the distinguishing
evidence is simply not in the text, no index/scorer/co-occurrence lever can recover it (the ceiling
finding, [[four-walls-research]]). "Distinctive presence" requires the gold option's FULL content
tokens (not one shared common word) so it measures real evidence, not incidental overlap. Retrieval
protocol is IDENTICAL to the oracle diagnostics (title-match + disk BM25 top-k), corpus swappable.

  python scripts/b2_measure_existence_gate.py [slice.jsonl] [--k 3]
Run now against the shipped LEAD corpus to reproduce the ~28.5% baseline (validates the instrument);
re-run after build_ring1_index over wiki_passages_en_body to measure the body-corpus lift. A body
result below 60% seals lever i honestly and hands the wall to representation (E9/Plan B).
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.reasoning_vm.ace.match_features import tokenize, _stem      # noqa: E402

DEFAULT_SLICE = REPO / "data" / "benchmarks" / "mmlu" / "slice_25_fresh.jsonl"
LEAD_PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
BODY_PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_body" / "passages.tsv"
_STOP = {"the", "a", "an", "of", "to", "in", "is", "and", "or", "for", "on", "at", "by", "with",
         "as", "it", "its", "this", "that", "which", "from", "are", "be", "was", "were", "than"}


def _content_stems(text: str) -> set[str]:
    return {_stem(w) for w in tokenize(text) if w.lower() not in _STOP and len(w) > 1}


def main() -> int:
    from packages.reasoning_vm.openbook import _SENT, load_disk_index, load_passages, retrieve

    k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 3
    corpus = BODY_PASSAGES if "--body" in sys.argv else LEAD_PASSAGES
    index_dir = None
    if "--index" in sys.argv:
        index_dir = sys.argv[sys.argv.index("--index") + 1]
    consumed = {str(k), index_dir}
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in consumed]
    path = Path(args[0]) if args else DEFAULT_SLICE
    if not path.exists():
        print(f"slice missing: {path}")
        return 1
    if not corpus.exists():
        print(f"corpus missing: {corpus} (run scripts/b2_build_fullarticle_corpus.py for --body)")
        return 1

    t0 = time.time()
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    passages = load_passages(str(corpus))
    di = load_disk_index(index_dir)
    print(f"slice={path.name} n={len(rows)} corpus={corpus.parent.name} index={'default' if not index_dir else index_dir} k={k}")

    present = fired = 0
    for r in rows:
        stem, ch, gold = r["question"], r["choices"], r["gold"]
        gtext = ch.get(gold)
        if gtext is None:
            continue
        texts = []
        got = retrieve(stem, passages, None)
        if got:
            texts.append(got[1])
        if di is not None:
            texts.extend(t for _ti, t in di.search_topk(stem, k=k))
        sents = [s for t in texts for s in _SENT.split(t) if len(s.strip()) >= 20][:60]
        if not sents:
            continue
        fired += 1
        passage_stems = set()
        for s in sents:
            passage_stems |= _content_stems(s)
        gold_stems = _content_stems(gtext)
        # DISTINCTIVE presence = the gold option's full content is in the retrieved text (all its
        # content stems), so a shared common word alone ("selection") does not count as evidence.
        if gold_stems and gold_stems <= passage_stems:
            present += 1

    n = len(rows)
    print(f"\nretrieval fired              : {fired}/{n}")
    print(f"GOLD distinctive presence    : {present / max(1, n):.4f}   [lead baseline 0.145 (this slice); gate >=0.60]")
    print(f"({round(time.time()-t0,1)}s)")
    print("\nread: this is the evidence-presence ceiling for lever i. Below 0.60 on the body corpus = the\n"
          "distinguishing evidence is absent even in article bodies -> lever i sealed, wall is E9's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
