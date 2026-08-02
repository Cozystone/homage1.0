# -*- coding: utf-8 -*-
"""Track F / F1 — LM-pretrain the realizer on real wiki prose for general FLUENCY (No-LLM).

F1 v0's degeneracy came from training only on 222k narrow bones->text pairs. The cure is more real
FLUENT text: the 3.15B-token wiki body corpus we just built is genuine human prose (not LLM output).
Plain causal-LM pretraining on it gives the decoder real English fluency; the bones->text fine-tune
(f1_train_realizer --warm) then adds grounding + the fact-dropout honesty. Encyclopedic register now;
conversational register waits on the dialogue datasets. No pretrained weights, No LLM.

  python scripts/f1_pretrain_realizer.py [max_tokens] [bs]
Saves data/graph_scale/realizer_pretrained.pt.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import torch
import torch.nn as nn
from tokenizers import Tokenizer

from packages.reasoning_vm.ace.realizer import Realizer, count_params

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
BODY = REPO / "data" / "graph_scale" / "wiki_passages_en_body" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "realizer_pretrained.pt"
CLS = 1
SEQ = 192


def _stream_blocks(tok: Tokenizer, need_tokens: int, seq: int):
    """Stream body paragraphs, tokenize, pack into fixed-length causal-LM blocks."""
    blocks, buf = [], [CLS]
    got = 0
    with BODY.open(encoding="utf-8", errors="ignore") as fh:
        while got < need_tokens:
            line = fh.readline()
            if not line:
                break
            tab = line.find("\t")
            if tab < 0:
                continue
            ids = tok.encode(line[tab + 1:].strip()).ids
            buf.extend(ids)
            got += len(ids)
            while len(buf) >= seq:
                blocks.append(buf[:seq])
                buf = [CLS] + buf[seq:]
    return np.array(blocks, dtype=np.int64)


def main() -> int:
    t0 = time.time()
    max_tokens = int(sys.argv[1]) if len(sys.argv) > 1 else 600_000_000
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    tok = Tokenizer.from_file(str(TOKJSON))
    V = tok.get_vocab_size()
    print(f"device {DEV} | vocab {V} | streaming ~{max_tokens:,} tokens of wiki prose…", flush=True)
    blocks = _stream_blocks(tok, max_tokens, SEQ)
    print(f"  {len(blocks):,} blocks x {SEQ} ({round(time.time()-t0,1)}s)", flush=True)

    model = Realizer(V).to(DEV)
    print(f"realizer {count_params(model)/1e6:.1f}M (tied head)", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, betas=(0.9, 0.98), weight_decay=0.01)
    steps = len(blocks) // bs
    warm = max(1, steps // 40)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    ce = nn.CrossEntropyLoss()
    rng = np.random.default_rng(0)
    order = rng.permutation(len(blocks))
    HARDCAP = 20 * 3600
    step = 0
    model.train()
    for i in range(0, len(order) - bs, bs):
        ids = torch.from_numpy(blocks[order[i:i + bs]]).to(DEV)
        with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
            logits = model(ids)
            loss = ce(logits[:, :-1].reshape(-1, logits.shape[-1]), ids[:, 1:].reshape(-1))
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step(); step += 1
        if step % 1000 == 0:
            print(f"    step {step}/{steps} loss {loss.item():.3f} ppl {np.exp(min(20,loss.item())):.1f} "
                  f"({round(time.time()-t0,1)}s)", flush=True)
        if time.time() - t0 > HARDCAP:
            break
    torch.save({"state": model.state_dict(), "vocab": V}, OUT)
    print(f"\nRESULT realizer_pretrain {{'saved': '{OUT.name}', 'blocks': {len(blocks)}, "
          f"'steps': {step}, 'final_loss': {round(loss.item(),3)}, 'elapsed_s': {round(time.time()-t0,1)}}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
