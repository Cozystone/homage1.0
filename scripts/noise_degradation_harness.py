# -*- coding: utf-8 -*-
"""Noise degradation curves — wall 2 (messy real-world text) first experiment.

Perturbs the clean evaluation items with the four noise families the robustness literature
identifies (keyboard typos at the NoiseQA rates, natural misspellings, case+punctuation strip,
question fragmentization) and measures, per family x rate:
  - strict accuracy (the degradation curve),
  - FLIP RATE (CheckList INV: fraction whose answer CHANGED vs clean — a flipped confident answer
    is the dangerous failure under hallucination-zero; an abstention is honest degradation),
  - abstention rate shift.
Anchors from the literature for context: natural keyboard noise (~9% of words) cost strong 2021
QA systems ~2.8 F1; 25% synthetic cost ~11 F1 (NoiseQA); transformers lose 20-40 points at 25%
misspelling (arXiv 2110.03353). Deterministic seed; every number reported.

  python scripts/noise_degradation_harness.py
"""
from __future__ import annotations

import json
import random
import re
import string
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer as sit_answer
from scripts.babi_external_harness import parse_task, grade, DATA

OUT = REPO / "data" / "comprehension" / "noise_degradation.json"

_QWERTY = {"q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij",
           "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv",
           "g": "fthb", "h": "gyjn", "j": "hukm", "k": "jil", "l": "kop", "z": "asx", "x": "zsdc",
           "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk"}
_NATURAL = {"received": "recieved", "believe": "beleive", "separate": "seperate", "which": "wich",
            "because": "becuase", "before": "befor", "going": "goin", "the": "teh", "and": "adn",
            "with": "wiht", "went": "wnet", "where": "wher", "there": "theer", "moved": "movd",
            "picked": "pikced", "kitchen": "kitchin", "bathroom": "bathrom", "garden": "gardin",
            "office": "offise", "hallway": "hallwya", "football": "footbal", "bedroom": "bedrom"}
_FUNC = {"the", "a", "an", "to", "of", "is", "was", "did", "do", "does"}


def _kb_typo(word: str, rng: random.Random) -> str:
    letters = [i for i, c in enumerate(word.lower()) if c in _QWERTY]
    if not letters:
        return word
    i = rng.choice(letters)
    sub = rng.choice(_QWERTY[word[i].lower()])
    return word[:i] + sub + word[i + 1:]


def perturb(text: str, family: str, rate: float, rng: random.Random) -> str:
    words = text.split()
    if family == "keyboard":
        return " ".join(_kb_typo(w, rng) if rng.random() < rate else w for w in words)
    if family == "natural":
        out = []
        for w in words:
            bare = w.strip(string.punctuation)
            if bare.lower() in _NATURAL and rng.random() < rate * 4:   # lexicon is sparse; scale up
                out.append(w.replace(bare, _NATURAL[bare.lower()]))
            else:
                out.append(w)
        return " ".join(out)
    if family == "case_punct":
        return re.sub(r"[^\w\s]", "", text).lower() if rate >= 0.25 else \
            (text.lower() if rate >= 0.10 else re.sub(r"[.!?]", "", text))
    if family == "fragment":                     # question fragmentization: drop function words
        return " ".join(w for w in words if not (w.lower().strip(string.punctuation) in _FUNC
                                                 and rng.random() < rate * 3))
    return text


def main() -> int:
    t0 = time.time()
    # item pool: bAbI valid qa1-qa8 (state organs) x 50 = 400 items — external, generative
    items = []
    for task in range(1, 9):
        n = 0
        for ctx, q, gold in parse_task(DATA / f"qa{task}_valid.txt"):
            if n >= 50:
                break
            items.append((ctx, q, gold))
            n += 1

    clean_answers = []
    clean_correct = 0
    for ctx, q, gold in items:
        a = sit_answer(q, build(ctx)).get("answer")
        clean_answers.append(a)
        clean_correct += 1 if grade(a, gold) == "correct" else 0
    n_items = len(items)
    report = {"n_items": n_items, "pool": "bAbI valid qa1-8 x50 (external)",
              "clean_acc": round(clean_correct / n_items, 4), "families": {}}
    print(f"clean acc {report['clean_acc']} on {n_items} items")

    for family in ("keyboard", "natural", "case_punct", "fragment"):
        report["families"][family] = {}
        for rate in (0.025, 0.10, 0.25):
            rng = random.Random(20260720)
            correct = flips = abstains = 0
            for (ctx, q, gold), clean_a in zip(items, clean_answers):
                pc = perturb(ctx, family, rate, rng)
                pq = perturb(q, family, rate, rng)
                a = sit_answer(pq, build(pc)).get("answer")
                g = grade(a, gold)
                correct += 1 if g == "correct" else 0
                abstains += 1 if a is None else 0
                if a != clean_a and a is not None and clean_a is not None:
                    flips += 1
            row = {"acc": round(correct / n_items, 4),
                   "delta_vs_clean": round(correct / n_items - report["clean_acc"], 4),
                   "flip_rate": round(flips / n_items, 4),
                   "abstain_rate": round(abstains / n_items, 4)}
            report["families"][family][str(rate)] = row
            print(f"  {family:<10} @{rate:<5} acc {row['acc']:.3f} (Δ{row['delta_vs_clean']:+.3f})  "
                  f"flip {row['flip_rate']:.3f}  abstain {row['abstain_rate']:.3f}")

    report["elapsed_s"] = round(time.time() - t0, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
