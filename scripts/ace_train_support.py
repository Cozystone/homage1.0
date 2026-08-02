# -*- coding: utf-8 -*-
"""DELIBERATOR D0 — train ACE's 3-way SUPPORT head (SUPPORTS / NEI / REFUTES) on the SAME body.

"Does the evidence support the claim?" is the judge the System-2 planner chains over. FEVER's essence is
claim↔evidence NLI; FEVER-with-evidence-text needs the wiki dump, so we train the identical capability on
self-contained NLI: MNLI (3-way: entailment→SUPPORTS, neutral→NEI, contradiction→REFUTES) + SciTail
(science entailment). Warm-starts from the SQuAD-trained ACE body (data/graph_scale/ace_squad.pt) so the
contextual encoder is reused, not rebuilt. No pretrained LLM.

  python scripts/ace_train_support.py [n_train] [epochs]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import torch                                                          # noqa: E402
from packages.reasoning_vm import learned_discriminator as LD        # noqa: E402
from packages.reasoning_vm.ace import data as D                      # noqa: E402
from packages.reasoning_vm.ace.model import AceEncoder, count_params  # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
CACHE = REPO / "data" / "benchmarks" / "nli"
_HDR = {"User-Agent": "ATANOR-train (research; blueyjkim@gmail.com)"}
LABELS = ["SUPPORTS", "NEI", "REFUTES"]


def _dl(url: str, path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=_HDR), timeout=240).read())
    return path


def _load_data(n: int):
    import pandas as pd
    rows = []
    # MNLI: 3-way. claim = hypothesis, evidence = premise. label 0=entail,1=neutral,2=contra → 0,1,2.
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/nyu-mll/glue/resolve/refs%2Fconvert%2Fparquet/mnli/train/0000.parquet",
            CACHE / "mnli_train.parquet"))
        for _i, r in df.iterrows():
            lab = int(r["label"])
            if lab in (0, 1, 2):
                rows.append((str(r["hypothesis"]), str(r["premise"]), lab))
    except Exception as e:
        print("  (MNLI skip)", str(e)[:70])
    # SciTail: science entailment → SUPPORTS/NEI (no refute). Adds domain flavor.
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/allenai/scitail/resolve/refs%2Fconvert%2Fparquet/snli_format/train/0000.parquet",
            CACHE / "scitail_train.parquet"))
        for _i, r in df.iterrows():
            lab = str(r.get("label") or r.get("gold_label") or "").lower()
            m = {"entailment": 0, "neutral": 1}.get(lab)
            if m is not None:
                rows.append((str(r["hypothesis"]), str(r["premise"]), m))
    except Exception as e:
        print("  (SciTail skip)", str(e)[:70])
    import random
    random.Random(0).shuffle(rows)
    return rows[:n]


def main():
    t0 = time.time()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 150000
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    print(f"device {DEV} | loading NLI…", flush=True)
    data = _load_data(n)
    print(f"  {len(data)} claim↔evidence pairs; class dist "
          f"{np.bincount([l for _c,_e,l in data]).tolist()}", flush=True)

    def _enc(rows):
        out = []
        for claim, ev, lab in rows:
            e = D.encode(tok, claim, ev)          # claim→CLS q-slot, evidence→p-slot
            e["support"] = lab
            out.append(e)
        return out

    val_n = min(6000, len(data) // 6)
    enc_val = _enc(data[:val_n])
    enc_tr = _enc(data[val_n:])
    print(f"  encoded {len(enc_tr)} train / {len(enc_val)} val ({round(time.time()-t0,1)}s)", flush=True)

    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    model._tok = tok
    ckpt = REPO / "data" / "graph_scale" / "ace_squad.pt"
    if ckpt.exists():                              # SAME BODY: reuse SQuAD-trained encoder
        sd = torch.load(ckpt, map_location=DEV)
        missing, unexpected = model.load_state_dict(sd, strict=False)
        print(f"  warm-started from ace_squad.pt (new: {len(missing)} support-head tensors)", flush=True)
    print(f"  params {count_params(model)/1e6:.1f}M | training support head + body…", flush=True)

    import random
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.01)
    steps = ((len(enc_tr) + 19) // 20) * epochs
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    ce = torch.nn.CrossEntropyLoss()
    step = 0
    for ep in range(epochs):
        idx = list(range(len(enc_tr)))
        random.Random(ep).shuffle(idx)
        model.train()
        for i in range(0, len(idx), 20):
            batch = [enc_tr[j] for j in idx[i:i + 20]]
            b = D.collate(batch, tok)
            b = {k: v.to(DEV) for k, v in b.items()}
            sup = torch.tensor([x["support"] for x in batch], device=DEV)
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                logits = model.support(b["ids"], b["seg"], b["feats"], b["pad"])
                loss = ce(logits, sup)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 400 == 0:
                print(f"    step {step}/{steps} loss {loss.item():.4f}", flush=True)

    # eval
    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for i in range(0, len(enc_val), 128):
            batch = enc_val[i:i + 128]
            b = D.collate(batch, tok)
            b = {k: v.to(DEV) for k, v in b.items()}
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                logits = model.support(b["ids"], b["seg"], b["feats"], b["pad"])
            preds.append(logits.argmax(-1).cpu().numpy())
            ys += [x["support"] for x in batch]
    preds = np.concatenate(preds); ys = np.array(ys)
    acc = float((preds == ys).mean())
    maj = float(np.bincount(ys).max() / len(ys))
    per = {LABELS[c]: round(float((preds[ys == c] == c).mean()), 3) for c in range(3) if (ys == c).any()}
    rep = {"val_acc": round(acc, 4), "majority": round(maj, 4), "per_class_recall": per,
           "n_train": len(enc_tr), "n_val": len(enc_val), "vs_majority": round(acc - maj, 4),
           "gate>majority": acc > maj + 0.05, "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT d0", json.dumps(rep))
    torch.save(model.state_dict(), REPO / "data" / "graph_scale" / "ace_support.pt")
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"ace_support_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
