# -*- coding: utf-8 -*-
"""WHY is GPQA closed-book BELOW random (0.1465 < 0.25 with full coverage)?

A scorer that answers everything and lands under the guess floor is not merely ignorant — it is
ANTI-correlated with the truth. On GPQA that has a known mechanism to check: the distractors are
expert-written to be plausible, i.e. stuffed with the question's own terminology, while the correct
option is often the less obvious phrasing. A token/evidence-OVERLAP scorer would then be biased
TOWARD distractors. This runner quantifies the structural biases WITHOUT the store (cheap) so the
fix targets the measured mechanism:

  · random-pick baseline (sanity: ~0.25)
  · fixed-position pick after the deterministic shuffle (~0.25 each if shuffle is fair)
  · LONGEST-option pick and SHORTEST-option pick (length bias of correct vs distractors)
  · QUESTION-TOKEN-OVERLAP pick — the store-free proxy of the evidence-overlap scorer: if picking
    the option sharing most tokens with the QUESTION already lands below random, the anti-signal
    is in surface overlap itself, before any graph evidence enters.

GPQA license (BINDING): the gated CSV is read from the gitignored cache; NO question/option text is
ever printed or stored — aggregate statistics only.
Run:  python scripts/diagnose_gpqa_below_random.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import random
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
CSV_PATH = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_STOP = {"the", "and", "for", "with", "that", "this", "which", "what", "are", "was", "were",
         "from", "into", "than", "then", "when", "where", "how", "why", "who", "can", "could",
         "would", "should", "will", "has", "have", "had", "not", "its", "his", "her", "their",
         "our", "your", "one", "two", "all", "each", "following", "correct", "true", "most"}


def _toks(s: str) -> set[str]:
    return {t for t in _WORD.findall(str(s).lower()) if t not in _STOP}


def _shuffled(question: str, correct: str, incorrect: list[str]) -> tuple[list[str], int]:
    """Same deterministic Fisher-Yates as benchmark_gpqa.py so positions match the real runs."""
    seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16)
    opts = [correct] + incorrect
    order = list(range(4))
    for i in range(3, 0, -1):
        seed, j = divmod(seed, i + 1)
        order[i], order[j] = order[j], order[i]
    shuffled = [opts[k] for k in order]
    return shuffled, shuffled.index(correct)


def main() -> int:
    if not CSV_PATH.exists():
        print("gated GPQA cache not present — nothing to diagnose")
        return 1
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    n = 0
    hit_random = 0
    hit_pos = [0, 0, 0, 0]
    hit_longest = hit_shortest = hit_overlap = hit_least_overlap = 0
    corr_len_rank_sum = 0.0          # 0 = shortest … 3 = longest
    corr_overlap_rank_sum = 0.0      # 0 = least question-overlap … 3 = most
    rng = random.Random(20260718)

    for r in rows:
        q = r.get("Question") or r.get("question") or ""
        correct = r.get("Correct Answer") or r.get("correct") or ""
        inc = [r.get(k) or "" for k in ("Incorrect Answer 1", "Incorrect Answer 2", "Incorrect Answer 3")]
        if not q or not correct or not all(inc):
            continue
        n += 1
        opts, ci = _shuffled(q, correct, inc)

        if rng.randrange(4) == ci:
            hit_random += 1
        for p in range(4):
            hit_pos[p] += 1 if p == ci else 0

        lens = [len(o) for o in opts]
        if lens.index(max(lens)) == ci:
            hit_longest += 1
        if lens.index(min(lens)) == ci:
            hit_shortest += 1
        corr_len_rank_sum += sorted(range(4), key=lambda i: lens[i]).index(ci)

        qt = _toks(q)
        ov = [len(qt & _toks(o)) for o in opts]
        # ties break toward the first max/min, same as an argmax scorer would
        if ov.index(max(ov)) == ci:
            hit_overlap += 1
        if ov.index(min(ov)) == ci:
            hit_least_overlap += 1
        corr_overlap_rank_sum += sorted(range(4), key=lambda i: ov[i]).index(ci)

    print(f"=== GPQA-Diamond structural diagnosis (n={n}, aggregates only) ===\n")
    print(f"  random pick                : {hit_random/n:.4f}   (sanity ~0.25)")
    print(f"  fixed position A/B/C/D     : {[round(h/n,3) for h in hit_pos]}   (shuffle fairness)")
    print(f"  pick LONGEST option        : {hit_longest/n:.4f}")
    print(f"  pick SHORTEST option       : {hit_shortest/n:.4f}")
    print(f"  pick MOST question-overlap : {hit_overlap/n:.4f}   <- store-free proxy of the evidence scorer")
    print(f"  pick LEAST question-overlap: {hit_least_overlap/n:.4f}")
    print(f"\n  correct answer's mean LENGTH rank  (0=shortest…3=longest): {corr_len_rank_sum/n:.3f} (unbiased=1.5)")
    print(f"  correct answer's mean OVERLAP rank (0=least…3=most)      : {corr_overlap_rank_sum/n:.3f} (unbiased=1.5)")
    print("\nReading: if MOST-overlap sits under 0.25 while LEAST-overlap sits over it, surface overlap")
    print("is an ANTI-signal on GPQA — expert distractors reuse the question's vocabulary — and the")
    print("0.1465 scorer inherited that bias. The honest fix is per-option entailment, not overlap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
