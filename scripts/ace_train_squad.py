# -*- coding: utf-8 -*-
"""ACE driver — train the contextual encoder on SQuAD-2 and measure against the pre-declared gates.

  python scripts/ace_train_squad.py m0            # sanity: overfit 1k (gate: train acc > 0.95)
  python scripts/ace_train_squad.py m1 [n] [ep]   # answerability (gate: internal val AUC >= 0.70)
  python scripts/ace_train_squad.py m2 [n] [ep]   # + span, score SEALED dev once (EM/F1, HasAns/NoAns)

dev-v2 is the frozen oracle: touched ONLY in m2, and the run records EM/F1 honestly whatever they are.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import torch                                                          # noqa: E402
from packages.reasoning_vm import learned_discriminator as LD        # noqa: E402
from packages.reasoning_vm.ace import data as D                      # noqa: E402
from packages.reasoning_vm.ace.model import AceEncoder, count_params  # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
_ART = {"a", "an", "the"}


# ── official SQuAD metric ──────────────────────────────────────────────────────────────────────
def _norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(pred, gold):
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    common = sum((Counter(p) & Counter(g)).values())
    if not common:
        return 0.0
    pr, rc = common / len(p), common / len(g)
    return 2 * pr * rc / (pr + rc)


def _best(pred, golds, m):
    return max((m(pred, g) for g in golds), default=m(pred, ""))


def _encode_rows(tok, rows):
    out = []
    for r in rows:
        e = D.encode(tok, r["q"], r["ctx"], r["ans_start"], r["ans_text"])
        e["answerable"] = r["answerable"]
        out.append(e)
    return out


def _batches(enc, bs, shuffle=True, seed=0):
    idx = np.arange(len(enc))
    if shuffle:
        np.random.default_rng(seed).shuffle(idx)
    for i in range(0, len(idx), bs):
        yield [enc[j] for j in idx[i:i + bs]]


def _train(model, enc, epochs, bs, lr, span_w=0.0, ans_w=1.0, seed=0, log_every=200, amp=True):
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = max(1, (len(enc) + bs - 1) // bs) * epochs
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(s / warm, 0.5 * (1 + np.cos(np.pi * max(0, s - warm) / max(1, steps - warm)))))
    bce = torch.nn.BCEWithLogitsLoss()
    ce = torch.nn.CrossEntropyLoss()
    step = 0
    model.train()
    for ep in range(epochs):
        for batch in _batches(enc, bs, seed=seed + ep):
            b = D.collate(batch, model._tok)
            b = {k: v.to(DEV) for k, v in b.items()}
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(amp and DEV == "cuda")):
                ans_logit, start, end = model(b["ids"], b["seg"], b["feats"], b["pad"])
                loss = ans_w * bce(ans_logit, b["answerable"])
                if span_w > 0 and b["has_span"].sum() > 0:
                    m = b["has_span"] > 0
                    loss = loss + span_w * 0.5 * (ce(start[m], b["start"][m]) + ce(end[m], b["end"][m]))
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % log_every == 0:
                print(f"    step {step}/{steps} loss {loss.item():.4f} lr {sched.get_last_lr()[0]:.2e}",
                      flush=True)


@torch.no_grad()
def _ans_probs(model, enc, bs=128):
    model.eval()
    out = []
    for batch in _batches(enc, bs, shuffle=False):
        b = D.collate(batch, model._tok)
        b = {k: v.to(DEV) for k, v in b.items()}
        with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
            ans_logit, _s, _e = model(b["ids"], b["seg"], b["feats"], b["pad"])
        out.append(torch.sigmoid(ans_logit).float().cpu().numpy())
    return np.concatenate(out)


@torch.no_grad()
def _decode(model, enc_row, ctx):
    b = D.collate([enc_row], model._tok)
    b = {k: v.to(DEV) for k, v in b.items()}
    with torch.autocast(DEV, dtype=torch.bfloat16, enabled=(DEV == "cuda")):
        ans_logit, start, end = model(b["ids"], b["seg"], b["feats"], b["pad"])
    p_ans = float(torch.sigmoid(ans_logit)[0])
    off, plen = enc_row["p_off"], enc_row["p_len"]
    s = start[0, off:off + plen].float().cpu().numpy()
    e = end[0, off:off + plen].float().cpu().numpy()
    ch = enc_row["p_char"]
    if not ch or plen == 0:
        return p_ans, ""
    # JOINT span: over the top-K start tokens, pick the (i,j) maximizing s[i]+e[j] with j in [i, i+30]
    best, bi, bj = -1e18, 0, 0
    for i in np.argsort(s)[::-1][:8]:
        i = int(i)
        w = e[i:i + 30]
        j = i + int(np.argmax(w))
        v = float(s[i] + e[j])
        if v > best:
            best, bi, bj = v, i, j
    return p_ans, ctx[ch[bi][0]:ch[min(bj, len(ch) - 1)][1]]


def _build(tok):
    import os
    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(DEV)
    mlm = REPO / "data" / "graph_scale" / os.getenv("ATANOR_MLM_CKPT", "ace_mlm_backbone.pt")
    if mlm.exists():                                  # M3: warm-start the whole encoder from self-MLM
        model.load_state_dict(torch.load(mlm, map_location=DEV), strict=False)
        print(f"  warm-started backbone from {mlm.name} (M3)", flush=True)
    model._tok = tok
    return model


def main():
    t0 = time.time()
    mode = sys.argv[1] if len(sys.argv) > 1 else "m0"
    nq = int(sys.argv[2]) if len(sys.argv) > 2 else 40000
    epochs = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    print(f"device {DEV} | vocab ids {tok.n_ids} | loading squad…", flush=True)
    train = D.load_squad("train")
    import random
    random.Random(0).shuffle(train)

    if mode == "m0":
        sub = train[:1000]
        enc = _encode_rows(tok, sub)
        model = _build(tok)
        print(f"params {count_params(model)/1e6:.1f}M | overfitting {len(sub)}…", flush=True)
        _train(model, enc, epochs=40, bs=64, lr=1e-3, span_w=0.0, log_every=200, amp=False)
        p = _ans_probs(model, enc)
        y = np.array([r["answerable"] for r in sub])
        acc = float(((p > 0.5).astype(int) == y).mean())
        print(f"\nRESULT m0 {json.dumps({'train_acc': round(acc,4), 'gate':'>0.95', 'pass': acc>0.95, 'elapsed_s': round(time.time()-t0,1)})}")
        return 0

    from sklearn.metrics import roc_auc_score
    tr = train[:nq]
    val = train[nq:nq + 4000]
    print(f"encoding {len(tr)} train + {len(val)} val…", flush=True)
    enc_tr, enc_val = _encode_rows(tok, tr), _encode_rows(tok, val)
    model = _build(tok)
    print(f"params {count_params(model)/1e6:.1f}M | training ({mode})…", flush=True)
    span_w = 1.0 if mode == "m2" else 0.0
    ans_w = 3.0 if mode == "m2" else 1.0        # keep answerability sharp under the heavier span loss
    bs = 20 if mode == "m2" else 48             # shared GPU: fit alongside the live vision/engine stack
    _train(model, enc_tr, epochs=epochs, bs=bs, lr=3e-4, span_w=span_w, ans_w=ans_w)

    pv = _ans_probs(model, enc_val)
    yv = np.array([r["answerable"] for r in val])
    auc = float(roc_auc_score(yv, pv))
    print(f"  internal-val answerability AUC {auc:.4f}", flush=True)

    if mode == "m1":
        print(f"\nRESULT m1 {json.dumps({'val_auc': round(auc,4), 'gate':'>=0.70', 'pass': auc>=0.70, 'train_q': len(tr), 'elapsed_s': round(time.time()-t0,1)})}")
        return 0

    # m2: score the SEALED dev once, official EM/F1 with the answerability gate
    dev = D.load_squad("dev")
    # tune abstain threshold on the internal val (NEVER dev) using the REAL SQuAD-2 F1 (decoded span
    # partial credit + abstain cost) — a proper operating-point search, not a binary proxy
    val_dec = []
    for r in val:
        er = D.encode(tok, r["q"], r["ctx"], r["ans_start"], r["ans_text"])
        pa, sp = _decode(model, er, r["ctx"])
        val_dec.append((pa, sp, r["golds"], r["answerable"]))
    best_thr, best = 0.5, -1.0
    for thr in [i / 40 for i in range(2, 38)]:
        f = np.mean([(1.0 if pa < thr else 0.0) if ansd == 0
                     else (_best(sp, g, _f1) if pa >= thr else 0.0)
                     for pa, sp, g, ansd in val_dec])
        if f > best:
            best, best_thr = f, thr
    print(f"  abstain threshold (val real-F1) = {best_thr}  (val_F1 {round(100*best,1)})", flush=True)

    em = f1 = 0.0
    has = has_f1 = no = no_ok = 0
    for r in dev:
        enc_row = D.encode(tok, r["q"], r["ctx"], r["ans_start"], r["ans_text"])
        p_ans, span = _decode(model, enc_row, r["ctx"])
        pred = span if p_ans >= best_thr else ""
        if r["answerable"] == 0:
            no += 1; ok = int(pred == ""); no_ok += ok; em += ok; f1 += ok
        else:
            has += 1
            e_, f_ = float(_best(pred, r["golds"], lambda a, b: float(_norm(a) == _norm(b)))), _best(pred, r["golds"], _f1)
            has_f1 += f_; em += e_; f1 += f_
    n = len(dev)
    rep = {"EM": round(100*em/n, 1), "F1": round(100*f1/n, 1),
           "HasAns_F1": round(100*has_f1/max(1, has), 1),
           "NoAns_abstain": round(100*no_ok/max(1, no), 1),
           "val_auc": round(auc, 4), "threshold": best_thr, "train_q": len(tr),
           "gates": {"HasAns_F1>=45": has_f1/max(1,has)*100 >= 45, "overall_F1>=55": 100*f1/n >= 55},
           "elapsed_s": round(time.time()-t0, 1)}
    print("\nRESULT m2", json.dumps(rep))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"ace_squad_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    torch.save(model.state_dict(), REPO / "data" / "graph_scale" / os.getenv("ATANOR_SQUAD_OUT", "ace_squad.pt"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
