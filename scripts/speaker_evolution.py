# -*- coding: utf-8 -*-
"""Run the speaker evolution arena on the real voice corpus (owner: 5 × 5 ).

 python scripts/speaker_evolution.py --pop 5 --generations 6 --workers 5

OFFLINE by design: the engine never runs this. It fits variant voices on the narrative
corpus, sits them on a sealed holdout exam (judged by the self-play Critic), and writes
 data/evolution/speaker_genome.json — the champion the live voice adopts ( )
 data/evolution/antibodies.jsonl — Critic-rejected token paths ( )
 data/evolution/arena_history.jsonl — every generation's fitness ()
No store, pack, or engine writes — the fact layer is out of reach by construction.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pop", type=int, default=5, help="agents per generation (사장님: 5마리)")
    ap.add_argument("--generations", type=int, default=6)
    ap.add_argument("--workers", type=int, default=5, help="worker processes ≈ cores (사장님: 5코어)")
    ap.add_argument("--corpus", type=int, default=1600, help="fit-corpus lines (balanced tail)")
    ap.add_argument("--holdout", type=int, default=300, help="sealed exam lines (never fit on)")
    args = ap.parse_args()

    from packages.autonomy_kernel.narrative_corpus import corpus_tail
    from packages.evolution.speaker_arena import evolve

    # one draw, then a hard split: the exam lines are REMOVED from what any genome may fit
    # on. rng-shuffled so the holdout isn't just "the newest diet" (which would drift with
    # the learner and make generations incomparable within a run).
    lines = corpus_tail(args.corpus + args.holdout, balanced=True)
    if len(lines) < 60:
        print(f"corpus too thin ({len(lines)} lines) — feed the diet first")
        return 1
    random.Random(11).shuffle(lines)
    holdout, fit_corpus = lines[:args.holdout], lines[args.holdout:]
    print(f"arena: fit={len(fit_corpus)} lines, sealed holdout={len(holdout)} lines, "
          f"pop={args.pop}, workers={args.workers}")

    t0 = time.time()
    out = evolve(fit_corpus, holdout, pop=args.pop, generations=args.generations,
                 workers=args.workers)
    champ = out["champion"]
    print(f"\ndone in {time.time()-t0:.0f}s — champion fitness={champ['fitness']} "
          f"(quality={champ['mean_quality']}, {champ['gen_s_per_line']}s/line)")
    print("champion genome:", champ["genome"])
    for line in champ["lines"][:4]:
        print(f"  [{line['total']:.2f}] {line['text'][:76]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
