# -*- coding: utf-8 -*-
"""DELIBERATOR D3.2 — teach the retrieval organ HotpotQA evidence selection. Full-pipeline F1 (0.205) is
now bounded by SUPPORT RECALL, not extraction (span organ is 0.53 on gold). So train the answerability
head (question, paragraph → is it a gold supporting fact?) on HotpotQA gold-vs-distractor, warm-started
from ace_hotpot.pt (which already has the multi-hop span). One model, both organs HotpotQA-tuned. Then
re-eval the full pipeline ranking by this learned relevance. No LLM.

  python scripts/ace_train_hotpot_rank.py [n_questions] [epochs]
"""
from __future__ import annotations

import ctypes
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _require_commit_headroom() -> None:
    """Fail clearly before importing torch when Windows commit is nearly exhausted."""
    if os.name != "nt":
        return

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return
    available_gib = status.ullAvailPageFile / (1024 ** 3)
    required_gib = float(os.getenv("ATANOR_D3_MIN_COMMIT_GIB", "20"))
    if available_gib < required_gib:
        raise SystemExit(
            f"D3.2 aborted before torch import: only {available_gib:.1f} GiB of Windows "
            f"commit is available; {required_gib:.1f} GiB is required. Stop stale training "
            "processes or restart the bloated :8502 engine, then retry."
        )


_require_commit_headroom()

import torch                                                          # noqa: E402
from packages.reasoning_vm import learned_discriminator as LD        # noqa: E402
from packages.reasoning_vm.ace import data as D                      # noqa: E402
from packages.reasoning_vm.ace.model import AceEncoder               # noqa: E402
from scripts.ace_train_hotpot import _rows, _f1, _norm               # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"


def _iter_pairs(path: Path, nq: int):
    """Stream the first *nq* questions as raw ranking pairs in bounded memory."""
    import pyarrow.parquet as pq

    rng = random.Random(0)
    seen = 0
    parquet = pq.ParquetFile(path)
    columns = ["question", "supporting_facts", "context"]
    for record_batch in parquet.iter_batches(batch_size=128, columns=columns):
        for row in record_batch.to_pylist():
            if seen >= nq:
                return
            seen += 1
            ctx = row["context"]
            titles, sents = list(ctx["title"]), list(ctx["sentences"])
            gold_titles = set(str(t) for t in row["supporting_facts"]["title"])
            gold_j = [j for j in range(len(titles)) if str(titles[j]) in gold_titles]
            dist_j = [j for j in range(len(titles)) if str(titles[j]) not in gold_titles]
            rng.shuffle(dist_j)
            question = str(row["question"])
            for j in gold_j + dist_j[:3]:
                paragraph = " ".join(str(x) for x in sents[j])
                yield question, paragraph, int(str(titles[j]) in gold_titles)


def _iter_shuffled_pairs(path: Path, nq: int, epoch: int, buffer_size: int):
    """Shuffle a stream with a fixed-size buffer instead of retaining the corpus."""
    rng = random.Random(epoch)
    buffer = []
    for pair in _iter_pairs(path, nq):
        if len(buffer) < buffer_size:
            buffer.append(pair)
            continue
        slot = rng.randrange(len(buffer))
        yield buffer[slot]
        buffer[slot] = pair
    rng.shuffle(buffer)
    yield from buffer


def _iter_encoded_batches(path: Path, nq: int, epoch: int, tok, batch_size: int):
    buffer_size = max(batch_size, int(os.getenv("ATANOR_D3_SHUFFLE_BUFFER", "2048")))
    batch = []
    for question, paragraph, relevant in _iter_shuffled_pairs(path, nq, epoch, buffer_size):
        encoded = D.encode(tok, question, paragraph)
        encoded.pop("p_char", None)
        encoded["rel"] = relevant
        batch.append(encoded)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    t0 = time.time()
    nq = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    train_path = REPO / "data" / "benchmarks" / "hotpotqa" / "train.parquet"
    print(f"device {DEV} | scanning (question,paragraph)->relevant pairs...", flush=True)
    pair_count = positive_count = 0
    for _question, _paragraph, relevant in _iter_pairs(train_path, nq):
        pair_count += 1
        positive_count += relevant
    print(f"  {pair_count} pairs (pos frac {positive_count / max(1, pair_count):.2f}) "
          f"streamed in bounded memory ({round(time.time()-t0,1)}s)", flush=True)

    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    hp = REPO / "data" / "graph_scale" / "ace_hotpot.pt"            # MLM + multi-hop span
    if hp.exists():
        model.load_state_dict(torch.load(hp, map_location=DEV), strict=False)
        print("  warm-started from ace_hotpot.pt (multi-hop span)", flush=True)
    model._tok = tok
    opt = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=0.01)
    bce = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(4.0, device=DEV))   # ~20% positive
    bs = 24
    steps = ((pair_count + bs - 1) // bs) * epochs
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    step = 0
    for ep in range(epochs):
        model.train()
        for batch in _iter_encoded_batches(train_path, nq, ep, tok, bs):
            b = D.collate(batch, tok)
            b = {k: v.to(DEV) for k, v in b.items()}
            rel = torch.tensor([x["rel"] for x in batch], dtype=torch.float32, device=DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                ans_logit, _s, _e = model(b["ids"], b["seg"], b["feats"], b["pad"])
                loss = bce(ans_logit, rel)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 800 == 0:
                print(f"    step {step}/{steps} loss {loss.item():.4f} ({round(time.time()-t0,1)}s)", flush=True)
    torch.save(model.state_dict(), REPO / "data" / "graph_scale" / "ace_hotpot.pt")

    # Do not retain the final CPU batch or optimizer state while evaluation loads its corpus.
    del batch, b, rel, loss, opt, sched
    import gc
    gc.collect()
    if DEV == "cuda":
        torch.cuda.empty_cache()

    # re-eval full pipeline ranking by the LEARNED relevance (answerability head)
    from packages.reasoning_vm.deliberator.planner import MultiHopReader
    rd = MultiHopReader.__new__(MultiHopReader)
    rd.torch, rd.D, rd.dev, rd.tok, rd.model = torch, D, DEV, tok, model
    model.eval()
    dev = _rows("dev_distractor", 1500)
    full_f1 = 0.0
    span_n = 0
    for r in dev:
        if r["yesno"]:
            continue
        span_n += 1
        out = rd.answer(r["q"], r["paras"], k=2, chain=False, rank="ans")
        full_f1 += _f1(out["answer"], r["ans"])
    rep = {"full_pipeline_F1_ans_rank": round(full_f1 / max(1, span_n), 4), "span_n": span_n,
           "prev_full_F1": 0.205, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d3.2", json.dumps(rep))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
