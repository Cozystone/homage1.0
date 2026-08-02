# -*- coding: utf-8 -*-
"""Track F / F1 — train the grounded neuro-symbolic realizer on (bones -> sentence) pairs.

Causal LM with loss only on the realisation span (the bones prefix is context). fact-dropout: a
fraction of samples blank the bones and target an honest ABSTENTION, so the model learns that no
bones => say nothing invented (knowing/saying separation, No-LLM). No pretrained weights, No LLM.

  python scripts/f1_train_realizer.py [n_pairs] [epochs] [bs]
Saves data/graph_scale/realizer.pt. Then scripts/f1_eval_realizer.py reports fluency proxy,
faithfulness, and the G-F3 closed-book abstention probe.

S1 recipe (Track F §8 — repair warm fine-tuning; two measured catastrophic-interference failures):
  --warm PATH        warm-start from the wiki-prose LM pretrain
  --untie            clone lm_head off the tied embedding (tied in+out gradients = suspect #1)
  --freeze-lower N   freeze tok_emb + the lowest N blocks (preserve pretrained grammar)
  --replay P         fraction of batch items trained as plain prose LM (classic anti-forgetting)
  --lr X             override the fine-tune lr (S1 prescribes 1e-5)
  --out NAME         checkpoint name (default realizer.pt; S1 runs save separately, baseline kept)
  --s1               shorthand: --untie --freeze-lower 4 --replay 0.25 --lr 1e-5 --out realizer_s1.pt
Gate S1 (pre-declared): warm loss < from-scratch 5.1 AND faithfulness >= 0.645 AND G-F3 stays 1.0.
"""
from __future__ import annotations

import json
import random
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
from packages.neural_emotion.endocrine import Neuromodulators
from packages.neural_emotion.integrity_monitor import scan, apply_damage

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
PAIRS = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
DLG = REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl"
REGISTER = REPO / "data" / "graph_scale" / "dialogue_register.jsonl"   # 245k human conversational lines (G2/S2)
OUT = REPO / "data" / "graph_scale" / "realizer.pt"
PAD, CLS, SEP = 0, 1, 2
MAXLEN = 224
OBJ_WORD_CAP = 24          # cap a bone object (e.g. a long WoW knowledge sentence) so the reply fits
FACT_DROPOUT = 0.15
ABSTAIN = "I don't have grounded information about that."
_REL = {"is_a": "is a", "alias": "also called", "located_in": "is located in", "capable_of": "can",
        "has_property": "is", "used_for": "is used for", "part_of": "is part of",
        "made_of": "is made of", "has_a": "has", "manner_of": "is a manner of",
        "defined_as": "is defined as"}


def _linearize(bones: list[list[str]]) -> str:
    parts = []
    for s, r, o in bones[:6]:
        o = " ".join(str(o).split()[:OBJ_WORD_CAP])          # cap long knowledge sentences
        parts.append(f"{s} {_REL.get(r, r.replace('_', ' '))} {o}")
    return "; ".join(parts)


def _encode_pair(tok: Tokenizer, bones: list[list[str]], text: str, drop: bool,
                 history: list[str] | None = None):
    hist = ""
    if history:
        hist = " | ".join(h[:120] for h in history[-3:]) + " || "
    if drop:
        prompt = hist + "bones: none"
        target = ABSTAIN
    else:
        prompt = hist + "bones: " + _linearize(bones)
        target = text
    t_ids = tok.encode(target).ids[: MAXLEN - 16] + [SEP]      # the REPLY gets priority, never cut off
    budget = MAXLEN - len(t_ids)
    p_body = tok.encode(prompt).ids
    p_ids = ([CLS] + p_body + [SEP])
    if len(p_ids) > budget:                                    # too long: drop the FRONT (oldest history)
        p_ids = [CLS] + p_body[-(budget - 2):] + [SEP]
    ids = p_ids + t_ids
    labels = [-100] * len(p_ids) + t_ids
    return ids, labels


def _encode_lm(tok: Tokenizer, text: str):
    """Replay sample: plain prose LM (the PRETRAIN task) — loss over the whole sentence, no bones
    prompt. Mixing these into fine-tune batches is the standard anti-catastrophic-forgetting move."""
    ids = [CLS] + tok.encode(text).ids[: MAXLEN - 2] + [SEP]
    labels = [-100] + ids[1:]
    return ids, labels


def _collate(batch):
    L = max(len(x[0]) for x in batch)
    ids = np.zeros((len(batch), L), np.int64)
    labels = np.full((len(batch), L), -100, np.int64)
    pad = np.ones((len(batch), L), bool)
    for i, (x, y) in enumerate(batch):
        ids[i, :len(x)] = x
        labels[i, :len(y)] = y
        pad[i, :len(x)] = False
    return (torch.from_numpy(ids), torch.from_numpy(labels), torch.from_numpy(pad))


def main() -> int:
    t0 = time.time()
    n_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 400000
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    bs = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    if not PAIRS.exists():
        print(f"no pairs at {PAIRS} — run scripts/f0_mine_bones_to_text.py first")
        return 1
    tok = Tokenizer.from_file(str(TOKJSON))
    V = tok.get_vocab_size()

    rows = []
    for src in (DLG, PAIRS):                     # dialogue first (P3b history conditioning), then facts
        if not src.exists():
            continue
        with src.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    if r.get("bones") and r.get("text"):
                        rows.append(r)
                except Exception:
                    continue
                if len(rows) >= n_pairs:
                    break
    random.Random(0).shuffle(rows)
    holdout = rows[:1000]
    train = rows[1000:]

    # G2/S2 lever: the replay ('prose LM') task can draw from the 245k human CONVERSATIONAL register
    # lines instead of the fact-sentence's own text, so the model learns dialogue register — the
    # measured fluency wall was register-corpus absence, and this is the corpus. Opt-in (--register)
    # so the S1 baseline is preserved; the objective is unchanged (plain LM), only the prose source.
    register_pool: list[str] = []
    if "--register" in sys.argv and REGISTER.exists():
        with REGISTER.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    t = (json.loads(line).get("text") or "").strip()
                except Exception:
                    continue
                if 12 <= len(t) <= 400:
                    register_pool.append(t)
        random.Random(1).shuffle(register_pool)
    print(f"device {DEV} | vocab {V} | train {len(train):,} | holdout {len(holdout)} | "
          f"register_replay {len(register_pool):,}", flush=True)

    # --- S1 recipe flags (shorthand --s1 expands to the full prescription) ---
    argv = list(sys.argv)
    if "--s1" in argv:
        argv += ["--untie", "--freeze-lower", "4", "--replay", "0.25", "--lr", "1e-5",
                 "--out", "realizer_s1.pt"]
    untie = "--untie" in argv
    freeze_n = int(argv[argv.index("--freeze-lower") + 1]) if "--freeze-lower" in argv else 0
    replay_p = float(argv[argv.index("--replay") + 1]) if "--replay" in argv else 0.0
    out_path = OUT.parent / (argv[argv.index("--out") + 1] if "--out" in argv else OUT.name)

    # MODEL SIZE (the fluency ceiling's lever): the register-data + decoding levers are exhausted —
    # rough English persists because a 35M from-scratch No-LLM model is capacity-bound. --d_model /
    # --layers let a larger realizer be trained (the honest next lever, compute-bound not code-bound).
    # The size is stored IN the checkpoint so the eval instantiates the matching architecture.
    d_model = int(argv[argv.index("--d-model") + 1]) if "--d-model" in argv else 512
    layers = int(argv[argv.index("--layers") + 1]) if "--layers" in argv else 8
    model = Realizer(V, d_model=d_model, layers=layers).to(DEV)
    if "--warm" in argv:                                 # warm-start from the wiki-prose LM pretrain
        wp = Path(argv[argv.index("--warm") + 1])
        if wp.exists():
            model.load_state_dict(torch.load(wp, map_location=DEV)["state"])
            print(f"  warm-started from {wp.name} (fluency pretrain)", flush=True)
    if untie:
        # S1 remedy 1: separate the LM head from the embedding — with a tied weight, input- and
        # output-side gradients strike the SAME tensor at once (interference suspect #1).
        model.lm_head.weight = nn.Parameter(model.tok_emb.weight.detach().clone())
        print("  head UNTIED from embedding", flush=True)
    if freeze_n > 0:
        # S1 remedy 2: freeze the embedding + lowest blocks — the pretrained grammar lives low.
        model.tok_emb.weight.requires_grad_(False)
        for b in model.blocks[:freeze_n]:
            for p in b.parameters():
                p.requires_grad_(False)
        print(f"  frozen: tok_emb + lowest {freeze_n} blocks", flush=True)
    print(f"realizer {count_params(model)/1e6:.1f}M params "
          f"({'untied' if untie else 'tied'} head, replay {replay_p})", flush=True)
    if "--lr" in argv:
        lr = float(argv[argv.index("--lr") + 1])         # S1 remedy 4: gentle lr (1e-5) + warmup
    else:
        lr = 3e-5 if "--warm" in argv else 1e-4
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=lr, betas=(0.9, 0.98), weight_decay=0.01)
    steps = (len(train) + bs - 1) // bs * epochs
    warm = max(1, steps // 25)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    ce = nn.CrossEntropyLoss(ignore_index=-100)
    rng = np.random.default_rng(0)
    step = 0
    hormones = Neuromodulators()                         # integrity self-damage: a cheat spikes cortisol
    loss_hist: list[float] = []
    # S1 remedy 4 — SOURCE-BUCKETED batches: short fact pairs and long dialogue pairs in one batch
    # produce the wild loss oscillation the first S1 run measured (7 -> 21 -> 13 -> 27). Each batch
    # is homogeneous by source (dialogue / facts); replay is its own whole-batch draw; batch ORDER
    # is shuffled so the mix over time is unchanged.
    dlg_idx = [i for i, r in enumerate(train) if r.get("history")]
    fact_idx = [i for i, r in enumerate(train) if not r.get("history")]
    for ep in range(epochs):
        buckets: list[tuple[str, list[int]]] = []
        for name, idx in (("dlg", dlg_idx), ("fact", fact_idx)):
            perm = rng.permutation(len(idx))
            for i in range(0, len(idx), bs):
                rows_b = [idx[j] for j in perm[i:i + bs]]
                kind = "replay" if (replay_p > 0 and rng.random() < replay_p) else name
                buckets.append((kind, rows_b))
        rng.shuffle(buckets)
        model.train()
        for kind, rows_b in buckets:
            batch = []
            for j in rows_b:
                r = train[j]
                if kind == "replay":
                    # S1 remedy 3: replay the pretrain task — plain prose LM. Prose source is the
                    # human CONVERSATIONAL register corpus when --register is on (the G2/S2 lever),
                    # else the fact-sentence's own text (S1 behaviour).
                    if register_pool:
                        text = register_pool[rng.integers(len(register_pool))]
                    else:
                        text = r["text"]
                    batch.append(_encode_lm(tok, text))
                    continue
                drop = rng.random() < FACT_DROPOUT
                batch.append(_encode_pair(tok, r["bones"], r["text"], drop, r.get("history")))
            ids, labels, pad = (t.to(DEV) for t in _collate(batch))
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
                logits = model(ids, pad)
                loss = ce(logits[:, :-1].reshape(-1, logits.shape[-1]), labels[:, 1:].reshape(-1))
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 500 == 0:
                loss_hist.append(loss.item())
                # integrity guard: if the loss collapses (a shortcut like the causal-mask copy bug),
                # cortisol spikes, lr_scale -> 0, and we REFUSE to save a gamed checkpoint.
                rep = scan({"loss_history": loss_hist})
                apply_damage(hormones, rep)
                if rep.cheated and hormones.rl_params()["lr_scale"] < 0.15:
                    print(f"\n[integrity] GAMING DETECTED -> cortisol {hormones.levels['cortisol']:.2f}, "
                          f"aborting without save. receipt={rep.receipt()}", flush=True)
                    return 2
                print(f"    step {step}/{steps} loss {loss.item():.3f} ({round(time.time()-t0,1)}s)", flush=True)
    torch.save({"state": model.state_dict(), "vocab": V, "untied": untie,
                "d_model": d_model, "layers": layers}, out_path)
    # keep a tiny holdout for the eval script (sealed-ish; separated by the same shuffle seed)
    (REPO / "data" / "graph_scale" / "realizer_holdout.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in holdout), encoding="utf-8")
    print(f"\nRESULT realizer {{'saved': '{out_path.name}', 'params_M': {round(count_params(model)/1e6,1)}, "
          f"'train': {len(train)}, 'steps': {step}, 'final_loss': {round(loss.item(), 3)}, "
          f"'elapsed_s': {round(time.time()-t0,1)}}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
