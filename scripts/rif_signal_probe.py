# -*- coding: utf-8 -*-
"""RIF signal probe — does a DSL feature carry ANY answerability signal, before asking the loop to
graduate it? Measures AUC + |point-biserial corr| of each candidate against the SQuAD-2 is_impossible
label directly. AUC 0.5 = none; >0.55 = real. This is the honest instrument that told us the SQuAD-2
gate wall is outside the ENTIRE static-embedding feature family (mean-pooled AND positional both ~0.5),
so no grammar within that family can break it — the next lever is a learned contextual encoder.

  python scripts/rif_signal_probe.py [n]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.reasoning_vm import learned_discriminator as LD          # noqa: E402
from packages.reasoning_vm.rif import dsl                              # noqa: E402
from packages.reasoning_vm.rif.dsl import Prog, Sig                    # noqa: E402
from scripts import train_squad as TS                                  # noqa: E402


def _signals(emb, ctx, q):
    content = [w for w in TS._TOK.findall(q.lower()) if w not in TS._QSTOP and len(w) > 1]
    focus, rest = content[:2] or content, content[2:] or content
    sents = [s for s in TS._SENT.split(ctx) if s.strip()][:8] or [ctx]
    pt = [emb.vecs[emb.idx[w]] for w in TS._TOK.findall(ctx.lower()) if w in emb.idx and len(w) > 1][:200]
    return {"q_focus": emb.embed(" ".join(focus)), "q_topic": emb.embed(" ".join(rest)),
            "q_all": emb.embed(q), "sents": np.array([emb.embed(s) for s in sents], np.float32),
            "ptoks": np.array(pt, np.float32) if pt else np.zeros((1, emb.dim), np.float32)}


def main() -> int:
    from sklearn.metrics import roc_auc_score
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    emb = LD.Embeddings.load(REPO / "data" / "graph_scale" / "rif_enwiki_emb")
    if emb is None:
        print("no enwiki embeddings; run scripts/rif_train_enwiki_emb.py first")
        return 1
    data = json.loads((TS.SQ / "train-v2.0.json").read_text(encoding="utf-8"))["data"]
    rows = [(p["context"], qa["question"], bool(qa.get("is_impossible")))
            for art in data for p in art["paragraphs"] for qa in p["qas"]]
    random.Random(0).shuffle(rows)
    rows = rows[:n]
    V, SV, TSEQ = dsl.V, dsl.SV, dsl.TSEQ
    feats = {
        "maxalign(sents,q_all)": Prog("maxalign", (Sig("sents", SV), Sig("q_all", V))),
        "sub(maxalign topic,focus)": Prog("sub", (Prog("maxalign", (Sig("sents", SV), Sig("q_topic", V))),
                                                  Prog("maxalign", (Sig("sents", SV), Sig("q_focus", V))))),
        "peak_align(ptoks,q_focus)": Prog("peak_align", (Sig("ptoks", TSEQ), Sig("q_focus", V))),
        "ctx_align(ptoks,focus,topic)": Prog("ctx_align", (Sig("ptoks", TSEQ), Sig("q_focus", V), Sig("q_topic", V))),
        "ctx_gap(ptoks,focus,topic)": Prog("ctx_gap", (Sig("ptoks", TSEQ), Sig("q_focus", V), Sig("q_topic", V))),
    }
    S = [_signals(emb, c, q) for c, q, _ in rows]
    y = np.array([int(i) for _, _, i in rows])
    print(f"n={len(y)}  impossible_frac={y.mean():.3f}\n{'feature':34s} {'AUC':>6s} {'|corr|':>7s}")
    for name, p in feats.items():
        col = np.array([dsl.evaluate(p, s) for s in S], float)
        col[~np.isfinite(col)] = 0.0
        auc = max(roc_auc_score(y, col), 1 - roc_auc_score(y, col)) if col.std() > 1e-9 else 0.5
        corr = abs(np.corrcoef(col, y)[0, 1]) if col.std() > 1e-9 else 0.0
        print(f"{name:34s} {auc:6.3f} {corr:7.3f}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
