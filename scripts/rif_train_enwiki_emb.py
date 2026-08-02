# -*- coding: utf-8 -*-
"""Train sharp self-supervised embeddings on the FULL-enwiki lead corpus and save them, so the RIF acid
test (and the discriminator / leap intuition) can run on a strong signal basis instead of the tiny
10k-context embeddings that carried ~zero SQuAD-2 answerability signal.

  python scripts/rif_train_enwiki_emb.py [n_passages] [max_vocab]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.reasoning_vm import learned_discriminator as LD          # noqa: E402

PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "rif_enwiki_emb"


def _stream(limit: int):
    corpus = []
    with open(PASSAGES, encoding="utf-8") as fh:
        for line in fh:
            tab = line.find("\t")
            if tab < 0:
                continue
            prose = line[tab + 1:].strip()
            if len(prose) > 40:
                corpus.append(prose)
                if len(corpus) >= limit:
                    break
    return corpus


def main() -> int:
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    max_vocab = int(sys.argv[2]) if len(sys.argv) > 2 else 80_000
    print(f"streaming up to {n} passages from full-enwiki…", flush=True)
    corpus = _stream(n)
    print(f"  loaded {len(corpus)} passages ({round(time.time()-t0,1)}s); training PPMI+SVD "
          f"(vocab≤{max_vocab})…", flush=True)
    emb = LD.train_embeddings(corpus, dim=LD._DIM, max_vocab=max_vocab, min_count=10)
    OUT.mkdir(parents=True, exist_ok=True)
    emb.save(OUT)
    # sanity: are the vectors meaningful?
    probes = [("king", "queen"), ("water", "liquid"), ("france", "paris"), ("einstein", "physics")]
    print(f"  vocab {len(emb.idx)}  ({round(time.time()-t0,1)}s). sanity cosines:", flush=True)
    for a, b in probes:
        ia, ib = emb.idx.get(a), emb.idx.get(b)
        if ia is not None and ib is not None:
            print(f"    {a}~{b}: {float(emb.vecs[ia] @ emb.vecs[ib]):.3f}", flush=True)
    print(f"SAVED {OUT} in {round(time.time()-t0,1)}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
