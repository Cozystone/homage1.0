# -*- coding: utf-8 -*-
"""SEALED C1 (comprehension) holdout — the ①/②/③-grade gate for the pillar, ENGLISH ONLY.

C1 is "utterance -> semantic frame": does ATANOR recover the compositional MEANING (speech act,
modality, polarity, prior-reference, self-address) rather than the surface tokens? The compositional
layer is a lexical pattern set, so the only honest measurement is a holdout containing lexical
realisations the patterns were NOT written against ('cheers', 'howdy', 'I'm knackered', 'gutted').
Those cases are included ON PURPOSE: a holdout that only repeats the tuned vocabulary would measure
memorisation and hide the ceiling that tells us when a LEARNED act classifier is required
([[rules-are-training-wheels]]).

Split is a stable hash of the utterance, so dev↔holdout gap is a real generalisation signal.
Run: python scripts/build_c1_battery.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "eval"

# (utterance, {slot: gold}). Vocabulary is deliberately varied — including items the current
# patterns do NOT list — so the holdout measures coverage, not recall of the tuning set.
CASES: list[tuple[str, dict]] = [
    # ── greeting / phatic (closed class, but many realisations)
    ("Hi", {"act": "greeting"}),
    ("Hello", {"act": "greeting"}),
    ("Hey there", {"act": "greeting"}),
    ("Good morning", {"act": "greeting"}),
    ("Good evening", {"act": "greeting"}),
    ("Thanks a lot", {"act": "greeting"}),
    ("Thank you so much", {"act": "greeting"}),
    ("Bye", {"act": "greeting"}),
    ("Goodbye for now", {"act": "greeting"}),
    ("See you later", {"act": "greeting"}),
    ("Cheers", {"act": "greeting"}),
    ("Howdy", {"act": "greeting"}),
    ("Morning!", {"act": "greeting"}),
    ("Nice to meet you", {"act": "greeting"}),
    # ── affect (experiencer frame + emotion)
    ("I'm so frustrated today", {"act": "affect"}),
    ("I feel exhausted", {"act": "affect"}),
    ("I'm really happy about this", {"act": "affect"}),
    ("I am anxious about tomorrow", {"act": "affect"}),
    ("I've been stressed all week", {"act": "affect"}),
    ("I'm thrilled with the result", {"act": "affect"}),
    ("I feel lonely lately", {"act": "affect"}),
    ("I'm absolutely gutted", {"act": "affect"}),
    ("I'm elated right now", {"act": "affect"}),
    ("I feel knackered", {"act": "affect"}),
    ("I am furious about it", {"act": "affect"}),
    ("I'm quite content", {"act": "affect"}),
    # ── correction
    ("No, that's not what I meant", {"act": "correction"}),
    ("Actually, I asked about something else", {"act": "correction"}),
    ("You misunderstood my question", {"act": "correction"}),
    ("That's wrong", {"act": "correction"}),
    ("I meant the other one", {"act": "correction"}),
    ("That is not what I said", {"act": "correction"}),
    # ── opinion
    ("What do you think about jazz?", {"act": "opinion"}),
    ("Your opinion on this?", {"act": "opinion"}),
    ("How do you feel about remote work?", {"act": "opinion"}),
    ("Do you believe that is true?", {"act": "opinion"}),
    ("Thoughts on the new design?", {"act": "opinion"}),
    ("What's your take on this?", {"act": "opinion"}),
    # ── query (+ interrogative modality)
    ("What is coffee?", {"act": "query", "modality": "interrogative"}),
    ("Where is the Eiffel Tower?", {"act": "query", "modality": "interrogative"}),
    ("Who wrote Hamlet?", {"act": "query", "modality": "interrogative"}),
    ("When did the war end?", {"act": "query", "modality": "interrogative"}),
    ("Why does ice float?", {"act": "query", "modality": "interrogative"}),
    ("Which planet is largest?", {"act": "query", "modality": "interrogative"}),
    ("Is gold a metal?", {"act": "query", "modality": "interrogative"}),
    ("Was Rome an empire?", {"act": "query", "modality": "interrogative"}),
    # ── request (+ imperative modality)
    ("Tell me how to install Python", {"act": "request", "modality": "imperative"}),
    ("Show me an example", {"act": "request", "modality": "imperative"}),
    ("Please explain recursion", {"act": "request", "modality": "imperative"}),
    ("Give me three options", {"act": "request", "modality": "imperative"}),
    ("Write a short summary", {"act": "request", "modality": "imperative"}),
    ("List the main causes", {"act": "request", "modality": "imperative"}),
    ("Summarize this for me", {"act": "request", "modality": "imperative"}),
    ("Help me understand entropy", {"act": "request", "modality": "imperative"}),
    ("Describe the process", {"act": "request", "modality": "imperative"}),
    ("Walk me through the steps", {"act": "request", "modality": "imperative"}),
    # ── statement / declarative
    ("Coffee is bad for you", {"modality": "declarative", "act": "statement"}),
    ("The library closes at six", {"modality": "declarative", "act": "statement"}),
    ("Water boils at 100 degrees", {"modality": "declarative", "act": "statement"}),
    ("My laptop has 16 gigabytes of memory", {"modality": "declarative", "act": "statement"}),
    # ── polarity
    ("That is not true", {"polarity": "negate"}),
    ("I don't agree with that", {"polarity": "negate"}),
    ("It isn't correct", {"polarity": "negate"}),
    ("He never finished it", {"polarity": "negate"}),
    ("Nothing was found", {"polarity": "negate"}),
    ("Yes, exactly", {"polarity": "affirm"}),
    ("That is correct", {"polarity": "affirm"}),
    ("Sounds right to me", {"polarity": "affirm"}),
    # ── prior reference (anaphora)
    ("Why is that?", {"refers_to_prior": True}),
    ("Explain that again", {"refers_to_prior": True}),
    ("What did you just say?", {"refers_to_prior": True}),
    ("Tell me more about it", {"refers_to_prior": True}),
    ("This is confusing", {"refers_to_prior": True}),
    ("Go back to the previous answer", {"refers_to_prior": True}),
    # ── NOT prior reference (complementiser 'that' must not fire)
    ("I think that coffee is good", {"refers_to_prior": False}),
    ("She said that the meeting moved", {"refers_to_prior": False}),
    ("What is a black hole?", {"refers_to_prior": False}),
    # ── self-address
    ("What can you do?", {"self_directed": True}),
    ("Tell me about yourself", {"self_directed": True}),
    ("Are you an AI?", {"self_directed": True}),
    ("What is photosynthesis?", {"self_directed": False}),
]


def _split(stem: str) -> str:
    return "holdout" if int(hashlib.sha1(stem.encode("utf-8")).hexdigest(), 16) % 100 < 35 else "dev"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [{"utterance": u, "gold": g, "split": _split(u)} for u, g in CASES]
    for split in ("dev", "holdout"):
        rows = [it for it in items if it["split"] == split]
        path = OUT / f"seal_c1_{split}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for it in rows:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        slots: dict[str, int] = {}
        for it in rows:
            for s in it["gold"]:
                slots[s] = slots.get(s, 0) + 1
        (OUT / f"seal_c1_{split}.manifest.json").write_text(
            json.dumps({"n": len(rows), "slot_counts": slots, "sha256": sha,
                        "built": "2026-07-18"}, indent=2), encoding="utf-8")
        print(f"[{split}] n={len(rows)} sha={sha[:12]} slots={slots}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
