# -*- coding: utf-8 -*-
"""RIF demonstration — the closed loop breaking a DESIGNED representation wall, deterministically.

The synthetic task is the SQuAD-gate structure in miniature: every sample "mentions the topic" (so the
base representation of topic-alignment is present but USELESS), and answerability depends entirely on
whether the asked FOCUS is present in the passage — a signal the base representation cannot see. A shallow
model on the base plateaus at chance. The loop must INVENT the focus-alignment program from the raw vector
signals and graduate it. This is the envelope expanding, proven end-to-end. No LLM.
"""
from __future__ import annotations

import numpy as np

from . import dsl
from .dsl import Prog, Sig
from .flywheel import Environment


def synthetic_env(n: int = 1400, dim: int = 16, seed: int = 0) -> Environment:
    rng = np.random.default_rng(seed)

    def _unit(v):
        return v / (np.linalg.norm(v) + 1e-9)

    samples, ys = [], []
    for _ in range(n):
        topic = _unit(rng.normal(size=dim))
        focus = _unit(rng.normal(size=dim))                 # ~orthogonal to topic in high-D
        noise1, noise2 = _unit(rng.normal(size=dim)), _unit(rng.normal(size=dim))
        unanswerable = rng.random() < 0.45
        sents = [_unit(topic + 0.15 * rng.normal(size=dim))]  # topic ALWAYS present
        if not unanswerable:
            sents.append(_unit(focus + 0.15 * rng.normal(size=dim)))   # focus present iff answerable
        sents.append(_unit(rng.normal(size=dim)))            # distractor sentences
        sents.append(_unit(rng.normal(size=dim)))
        rng.shuffle(sents)
        samples.append({"sents": np.array(sents, np.float32), "topic": topic.astype(np.float32),
                        "focus": focus.astype(np.float32), "noise1": noise1.astype(np.float32),
                        "noise2": noise2.astype(np.float32)})
        ys.append(int(unanswerable))

    y = np.array(ys)
    idx = rng.permutation(n)
    tr, va, ho = idx[: n * 6 // 10], idx[n * 6 // 10: n * 8 // 10], idx[n * 8 // 10:]
    signals = [Sig("sents", dsl.SV), Sig("topic", dsl.V), Sig("focus", dsl.V),
               Sig("noise1", dsl.V), Sig("noise2", dsl.V)]
    # BASE representation: topic-alignment only — present but blind to answerability (the wall).
    base = [Prog("maxalign", (Sig("sents", dsl.SV), Sig("topic", dsl.V))),
            Prog("meanalign", (Sig("sents", dsl.SV), Sig("topic", dsl.V)))]
    return Environment(name="synthetic_gate", signals=signals, samples=samples, y=y,
                       train_idx=tr, val_idx=va, holdout_idx=ho, basis=base, goal=0.9,
                       model_spec="gbm:0.1")


def main():
    import json
    import sys
    from .flywheel import run_loop
    sys.stdout.reconfigure(encoding="utf-8")
    env = synthetic_env()
    print("RIF demo — closing the loop on a designed representation wall\n", flush=True)
    rep = run_loop(env, rounds=6, n=70, seed=0, margin=0.01, verbose=True)
    print("\nRESULT", json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
