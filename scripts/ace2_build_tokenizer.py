# -*- coding: utf-8 -*-
"""ACE2 Phase A — train the byte-level BPE (16k) and run the HARD span-alignment gate. A byte-level BPE is
LOSSLESS (every byte is recoverable) and carries offset mappings, so an extractive answer span always
reconstructs to the exact characters. This gate must pass BEFORE any GPU is spent — a broken tokenizer
would silently re-create the span-F1 ceiling. No pretrained weights: the tokenizer is TRAINED from our
enwiki, a training tool like the optimizer. No LLM.

  python scripts/ace2_build_tokenizer.py [vocab] [train_mb]
Saves: data/graph_scale/ace2_tokenizer/tokenizer.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CORPUS = REPO / "data" / "graph_scale" / "wiki_passages_en" / "passages.tsv"     # 126MB sample
SQUAD = REPO / "data" / "benchmarks" / "squad2" / "train-v2.0.json"
OUTDIR = REPO / "data" / "graph_scale" / "ace2_tokenizer"
SPECIALS = ["<pad>", "<cls>", "<sep>", "<mask>", "<unk>", "<s>"]   # ids 0..5


def _corpus_iter(max_bytes: int):
    seen = 0
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            t = line.find("\t")
            text = line[t + 1:] if t >= 0 else line
            seen += len(text.encode("utf-8"))
            yield text.strip()
            if seen >= max_bytes:
                return


def main():
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders
    t0 = time.time()
    vocab = int(sys.argv[1]) if len(sys.argv) > 1 else 16384
    train_mb = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    print(f"training byte-BPE vocab={vocab} on ~{train_mb}MB…", flush=True)

    tok = Tokenizer(models.BPE(unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=True)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=vocab, special_tokens=SPECIALS, min_frequency=2)
    tok.train_from_iterator(_corpus_iter(train_mb * 1024 * 1024), trainer=trainer)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    tok.save(str(OUTDIR / "tokenizer.json"))
    print(f"  vocab {tok.get_vocab_size()} saved ({round(time.time()-t0,1)}s)", flush=True)

    # ---- HARD GATE: extractive span char-roundtrip on real SQuAD answers ----
    data = json.loads(SQUAD.read_text(encoding="utf-8"))["data"]
    pairs = []
    for art in data:
        for para in art["paragraphs"]:
            ctx = para["context"]
            for qa in para["qas"]:
                if qa.get("is_impossible") or not qa.get("answers"):
                    continue
                a = qa["answers"][0]
                pairs.append((ctx, a["answer_start"], a["text"]))
                if len(pairs) >= 10000:
                    break
            if len(pairs) >= 10000:
                break
        if len(pairs) >= 10000:
            break

    ok = 0
    for ctx, a0, atext in pairs:
        a1 = a0 + len(atext)
        enc = tok.encode(ctx)
        offs = enc.offsets
        hit = [k for k, (s, e) in enumerate(offs) if s < a1 and e > a0]     # tokens overlapping the answer
        if not hit:
            continue
        recon = ctx[offs[hit[0]][0]:offs[hit[-1]][1]]                       # minimal covering token span
        if atext.strip() in recon:                                         # gold recoverable from tokens
            ok += 1
    rate = ok / max(1, len(pairs))
    rep = {"vocab": tok.get_vocab_size(), "n_answers": len(pairs), "char_roundtrip": round(rate, 5),
           "GATE_pass": rate >= 0.999, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT ace2_tokenizer", json.dumps(rep))
    if not rep["GATE_pass"]:
        print("GATE FAILED — do NOT spend GPU. Fix tokenizer/alignment first.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
