# -*- coding: utf-8 -*-
"""Detached long-run: sense-aware order mining over enwiki-full (24GB bz2), with periodic pruning
so the context Counter stays in RAM. Appends progress to data/temporal_reasoning/enwiki_full.log and
merges results into order_counts.json / ctx_counts.json at the end."""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.temporal_reasoning.order_miner import iter_corpus_lines, sentence_pairs_ctx  # noqa: E402

OUT = ROOT / "data" / "temporal_reasoning"
LOG = OUT / "enwiki_full.log"
SRC = ROOT / "data" / "knowledge_sources" / "enwiki-full.xml.bz2"
PRUNE_EVERY = 20_000_000          # lines between ctx-singleton prunes (RAM guard)


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def main() -> None:
    pair: Counter = Counter()
    ctx: Counter = Counter()
    t0, n = time.time(), 0
    for line in iter_corpus_lines(SRC):
        n += 1
        if n % 5_000_000 == 0:
            log(f"{n/1e6:.0f}M lines, pairs={len(pair)}, ctx={len(ctx)}, {time.time()-t0:.0f}s")
        if n % PRUNE_EVERY == 0:
            before = len(ctx)
            ctx = Counter({k: v for k, v in ctx.items() if v >= 2})
            log(f"pruned ctx singletons: {before} -> {len(ctx)}")
        for a, b, cs in sentence_pairs_ctx(line):
            pair[(a, b)] += 1
            for c in cs:
                ctx[(c, a, b)] += 1
    log(f"DONE mining: {n} lines, pairs={len(pair)} obs={sum(pair.values())}, ctx={len(ctx)}")

    # merge into existing stores (keep the tatoeba/simplewiki/chunk1 signal)
    old_pair = Counter({tuple(k.split("|")): v for k, v in
                        json.loads((OUT / "order_counts.json").read_text()).items()})
    old_ctx = Counter({tuple(k.split("|")): v for k, v in
                       json.loads((OUT / "ctx_counts.json").read_text()).items()})
    old_pair.update(pair)
    old_ctx.update(ctx)
    (OUT / "order_counts.json").write_text(
        json.dumps({f"{a}|{b}": v for (a, b), v in old_pair.items()}))
    (OUT / "ctx_counts.json").write_text(
        json.dumps({f"{c}|{a}|{b}": v for (c, a, b), v in old_ctx.items() if v >= 2}))
    log(f"MERGED+SAVED: pairs={len(old_pair)} obs={sum(old_pair.values())} ctx(>=2)="
        f"{sum(1 for v in old_ctx.values() if v >= 2)}")


if __name__ == "__main__":
    main()
