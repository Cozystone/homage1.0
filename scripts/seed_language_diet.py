# -*- coding: utf-8 -*-
"""Seed the language diet — aim the (already-steered) web miner at the STARVED registers: Korean
dialogue and English (owner 2026-07-12: " … 
, ").

Two honest moves, no fabricated content:
 1. STEER — register / topics as diet-mining targets, so browse_director aims the real web
 expedition at conversational + English sources (Tatoeba, OpenSubtitles, English Wikipedia). The
 corpus grows from real reads, not authored templates — this is the scalable path.
 2. PRIME — feed a SMALL set of genuine bilingual EXAMPLE sentences into the voice corpus so the
 holographic voice has some English + spoken-register material to fit on immediately. These are
 plain example sentences (surface register), never facts and never an answer-lane template.

For bulk: drop a Tatoeba/OpenSubtitles JSONL and run scripts/feed_dataset.py (the ingest pipeline
already exists: corpus_adapters.iter_tatoeba_sentences / iter_oscar_sentences). This script only
primes + steers; it does not pretend to BE a dataset.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Genuine example sentences — spoken Korean register + English (SVO, different word order from
# Korean SOV). Small on purpose; the real volume comes from the steered miner + a real dataset.
_PRIME_KO = [
    "요즘 어떻게 지내? 나는 그럭저럭 지내고 있어.",
    "그 얘기 들으니까 나도 마음이 좀 놓인다.",
    "오늘 하루도 수고 많았어. 푹 쉬어.",
    "그건 좀 아쉽긴 한데, 다음엔 더 잘 될 거야.",
    "네 말이 무슨 뜻인지 알 것 같아. 조금 더 얘기해 줄래?",
    "괜찮아, 천천히 해도 돼. 급할 거 없어.",
]
_PRIME_EN = [
    "How are you doing these days? I've been getting by, thanks.",
    "I'm glad to hear that — it puts my mind at ease too.",
    "That's a little disappointing, but it'll go better next time.",
    "I think I see what you mean. Could you tell me a bit more?",
    "Take your time; there's no rush at all.",
    "The cat sat quietly by the window while the rain kept falling.",
]


def main() -> int:
    # 1) steer the miner toward the starved registers
    try:
        from packages.evolution.diet_steering import record_weakness, status
        # a strong pull (low pseudo-score) on conversational + English topics
        targets = [("대화", 0.1), ("영어", 0.1), ("회화", 0.15), ("english", 0.1), ("dialogue", 0.15)]
        n = record_weakness(targets, floor=0.6)
        print(f"steered miner toward {n} starved register(s): {[t for t, _ in targets]}")
        print("  live targets:", status()["targets"])
    except Exception as exc:
        print(f"steering skipped: {type(exc).__name__}: {exc}")

    # 2) prime the voice corpus with genuine bilingual example sentences (surface lane only)
    try:
        from packages.autonomy_kernel.narrative_corpus import add_lines
        added = add_lines(_PRIME_KO + _PRIME_EN, source="language_diet_seed")
        print(f"primed voice corpus with {added} bilingual example line(s) (surface register)")
    except Exception as exc:
        print(f"priming skipped: {type(exc).__name__}: {exc}")

    print("\nfor bulk: drop a Tatoeba/OpenSubtitles JSONL and run "
          "`python scripts/feed_dataset.py <file> --license <lic>` (adapters already exist).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
