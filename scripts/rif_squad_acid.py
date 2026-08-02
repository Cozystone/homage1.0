# -*- coding: utf-8 -*-
"""RIF ACID TEST — run the Representation Invention Flywheel on the REAL SQuAD 2.0 answerability gate.

The prober flagged the gate a representation_wall (memorization caps 0.561, classes entangled). Here the
loop must INVENT a program — from raw vector signals it is GIVEN — that breaks that wall on a sealed
holdout, WITHOUT anyone hand-writing the compositional feature. Signals exposed are LAD surface
decompositions of the question (focus vs topic vs whole) + the passage sentences; the DECISION of how to
combine them is 100% the learned loop. Honest: whatever it reaches is reported, gaming forbidden.

  python scripts/rif_squad_acid.py [n_questions]
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.reasoning_vm import learned_discriminator as LD          # noqa: E402
from packages.reasoning_vm.rif import dsl                              # noqa: E402
from packages.reasoning_vm.rif.dsl import Prog, Sig                    # noqa: E402
from packages.reasoning_vm.rif.flywheel import Environment, run_loop, save_basis   # noqa: E402
from scripts import train_squad as TS                                  # noqa: E402


def _signals(emb, ctx: str, q: str) -> dict:
    """Raw vector signals for one question — LAD surface decomposition (topic/focus/whole) + sentences."""
    content = [w for w in TS._TOK.findall(q.lower()) if w not in TS._QSTOP and len(w) > 1]
    focus = content[:2] or content                       # first content words ≈ the asked thing
    rest = content[2:] or content                        # the rest ≈ topic/entity
    sents = [s for s in TS._SENT.split(ctx) if s.strip()][:8] or [ctx]
    # ORDERED passage token vectors (the grammar-amendment signal): every in-vocab content token, in
    # passage order, capped for cost. Enables ctx_align/peak_align — positional, un-pooled.
    ptok_vecs = [emb.vecs[emb.idx[w]] for w in TS._TOK.findall(ctx.lower())
                 if w in emb.idx and len(w) > 1][:200]
    ptoks = np.array(ptok_vecs, np.float32) if ptok_vecs else np.zeros((1, emb.dim), np.float32)
    return {
        "q_all": emb.embed(q).astype(np.float32),
        "q_focus": emb.embed(" ".join(focus)).astype(np.float32),
        "q_focus1": emb.embed(content[0] if content else q).astype(np.float32),
        "q_topic": emb.embed(" ".join(rest)).astype(np.float32),
        "sents": np.array([emb.embed(s) for s in sents], np.float32),
        "ptoks": ptoks,
    }


def main() -> int:
    t0 = time.time()
    nq = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    train = json.loads((TS.SQ / "train-v2.0.json").read_text(encoding="utf-8"))["data"]
    rows = []
    for art in train:
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                rows.append((para["context"], qa["question"], bool(qa.get("is_impossible"))))
    random.Random(0).shuffle(rows)
    enwiki = REPO / "data" / "graph_scale" / "rif_enwiki_emb"
    emb = LD.Embeddings.load(enwiki) if enwiki.exists() else None
    if emb is not None:
        print(f"loaded FULL-ENWIKI embeddings: vocab {len(emb.idx)}, dim {emb.dim}", flush=True)
    else:
        ctxs = list({c for c, _q, _i in rows[: nq * 3]})
        print(f"training embeddings on {len(ctxs)} contexts (no enwiki emb found)…", flush=True)
        emb = LD.train_embeddings(ctxs, dim=LD._DIM)
    rows = rows[:nq]

    print(f"building signals for {len(rows)} questions…", flush=True)
    samples, y = [], []
    for ctx, q, imp in rows:
        samples.append(_signals(emb, ctx, q))
        y.append(int(imp))
    y = np.array(y)
    n = len(y)
    idx = np.random.RandomState(0).permutation(n)
    tr, va, ho = idx[: n * 6 // 10], idx[n * 6 // 10: n * 8 // 10], idx[n * 8 // 10:]

    signals = [Sig("sents", dsl.SV), Sig("ptoks", dsl.TSEQ), Sig("q_all", dsl.V), Sig("q_focus", dsl.V),
               Sig("q_focus1", dsl.V), Sig("q_topic", dsl.V)]
    # BASE = EMPTY → the honest baseline is majority-class; the loop must invent answerability signal
    # from scratch and BEAT majority on a sealed holdout. Nothing is hand-written.
    maj = float(max(y.mean(), 1 - y.mean()))
    env = Environment(name="squad_gate_acid", signals=signals, samples=samples, y=y,
                      train_idx=tr, val_idx=va, holdout_idx=ho, basis=[],
                      goal=round(maj + 0.04, 3), model_spec="gbm:0.1")
    print(f"  n={n}  majority={maj:.3f}  goal={env.goal}  ({round(time.time()-t0,1)}s)", flush=True)

    rep = run_loop(env, rounds=6, n=150, seed=0, margin=0.005, patience=3, verbose=True)
    rep["majority_baseline"] = round(maj, 4)
    rep["elapsed_s"] = round(time.time() - t0, 1)
    save_basis(env)
    print("\nRESULT", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"rif_squad_acid_{time.strftime('%Y%m%d_%H%M')}.json"
     ).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
