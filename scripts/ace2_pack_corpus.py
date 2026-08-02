# -*- coding: utf-8 -*-
"""ACE2 Phase A(late) — pack the FULL English corpus into a uint16 token memmap, once, on CPU.

Why this exists (2026-07-18, E9 preflight): the shipped RTD trainer streams packed sequences
into an in-RAM int64 buffer, which caps a full run at ~3M seqs = 384M tokens — 43% of the
corpus seen once, versus the design's 0.9B x 2-3 epochs. Multi-epoch over a small buffer
would break the <=4-epoch data-constrained rule (Muennighoff), and int64 for a 16,384 vocab
wastes 4x RAM. A one-time uint16 pack on disk (~1.8GB) lets the trainer memmap random windows:
full corpus, true epochs, near-zero RAM, and the OS page cache does the caching.

Output: data/graph_scale/ace2_pack/tokens_u16.bin + meta.json  (gitignored; rebuildable)
Usage:  python scripts/ace2_pack_corpus.py            # ~10-20 min CPU, batched encode
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
PASSAGES = REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"
OUTDIR = REPO / "data" / "graph_scale" / "ace2_pack"
SEP = 2
BATCH = 8192            # texts per encode_batch call (tokenizers parallelises internally)


def main() -> int:
    from tokenizers import Tokenizer
    t0 = time.time()
    tok = Tokenizer.from_file(str(TOKJSON))
    V = tok.get_vocab_size()
    assert V <= 65536, "uint16 pack requires vocab <= 65536"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    bin_path = OUTDIR / "tokens_u16.bin"
    n_tokens = n_docs = 0
    buf: list[str] = []
    with open(bin_path, "wb") as out, open(PASSAGES, encoding="utf-8") as fh:
        def flush():
            nonlocal n_tokens, n_docs
            if not buf:
                return
            encs = tok.encode_batch(buf)
            ids: list[int] = []
            for e in encs:
                ids.extend(e.ids)
                ids.append(SEP)                      # doc boundary marker inside the stream
            arr = np.asarray(ids, dtype=np.uint16)
            arr.tofile(out)
            n_tokens += len(arr)
            n_docs += len(buf)
            buf.clear()

        for line in fh:
            t = line.find("\t")
            text = (line[t + 1:] if t >= 0 else line).strip()
            if len(text) < 40:
                continue
            buf.append(text)
            if len(buf) >= BATCH:
                flush()
                if n_docs % (BATCH * 32) == 0:
                    el = time.time() - t0
                    print(f"  {n_docs:,} docs  {n_tokens:,} tokens  ({el:.0f}s, "
                          f"{n_tokens / max(1, el) / 1e6:.1f}M tok/s)", flush=True)
        flush()
    meta = {"n_tokens": n_tokens, "n_docs": n_docs, "vocab": V, "dtype": "uint16", "sep": SEP,
            "source": str(PASSAGES.relative_to(REPO)), "built_ts": int(time.time()),
            "elapsed_s": round(time.time() - t0, 1)}
    (OUTDIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nRESULT ace2_pack {json.dumps(meta)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
