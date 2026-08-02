# -*- coding: utf-8 -*-
"""Data-derived ACT lexicons (greeting / emotion) for the C1 comprehension layer — READ-ONLY sidecar.

WHY NOT A HAND LIST
    The sealed C1 holdout measured the ceiling of hand-written act patterns: 'Cheers', 'Howdy',
    'Morning!', 'knackered', 'elated' all missed, because a hand list cannot enumerate an open
    class. Adding those words after seeing the holdout would be tuning to the sealed set — the
    exact illusion the discipline forbids. So the lexicon is DERIVED from the dictionary instead,
    independently of the battery: a word joins a class when Wiktionary/Kaikki GLOSSES say so.

    Crucially this scans ALL senses, not the primary one: the greeting/emotion reading is usually
    secondary ('cheers' is primarily the toast verb, 'livid' primarily a colour), which is why a
    primary-gloss-only derivation caught barely half.

METHOD
    * GREETING — any sense whose gloss names the speech act (greeting, salutation, farewell,
      parting, toast, expression of gratitude/thanks, 'used to greet').
    * EMOTION  — any sense whose gloss contains a GENERIC seed emotion term. The seed is ordinary
      emotion vocabulary (not drawn from the battery); the dictionary expands it to thousands of
      words, so 'knackered'→"Tired or exhausted" and 'elated'→"Extremely happy…" are captured by
      derivation rather than by hand.

Run:  python scripts/build_act_lexicon.py
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "graph_scale" / "act_lexicon.json"

_GREETING_GLOSS = re.compile(
    r"\b(a |an )?(informal |formal |friendly |casual |standard )?"
    r"(greeting|salutation|farewell|valediction|goodbye|parting (word|phrase|salutation))\b"
    r"|used (to|when) (greet|say (hello|goodbye|farewell)|address someone)"
    r"|expression of (gratitude|thanks|appreciation)"
    r"|\bas a toast\b|\bon parting\b|\bwhen meeting\b", re.IGNORECASE)

# GENERIC emotion seed — ordinary vocabulary, deliberately NOT taken from the sealed battery.
_EMO_SEED = (r"happy|happiness|sad|sadness|angry|anger|afraid|fear|fearful|tired|exhausted|weary|"
             r"excited|excitement|pleased|pleasure|upset|anxious|anxiety|worried|worry|lonely|"
             r"depressed|depression|joy|joyful|delighted|delight|grateful|gratitude|nervous|"
             r"annoyed|annoyance|ashamed|shame|proud|pride|jealous|envy|disgusted|disgust|"
             r"embarrassed|frustrated|frustration|content|contented|miserable|misery|"
             r"enthusiastic|irritated|resentful|hopeful|despair|grief|elation|euphoric|calm|"
             r"relaxed|stressed|overwhelmed|relieved|disappointed|bored|boredom|furious|"
             r"melancholy|longing|yearning|affection|love|hate|hatred")
_EMOTION_GLOSS = re.compile(
    rf"\b({_EMO_SEED})\b|\b(feeling|emotion|mood|state of mind) (of|that)\b", re.IGNORECASE)
# a gloss that merely MENTIONS an emotion word about someone else is still fine — the frame's
# experiencer guard ('I am/feel …') is what prevents topic statements from reading as affect.

_HANGUL = re.compile(r"[가-힣]")
_WS = re.compile(r"\s+")
_WORD_OK = re.compile(r"^[a-z][a-z'\- ]{0,24}$")   # ordinary lower-case headwords only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=str(REPO / "data" / "graph_scale" / "kaikki-en.jsonl.gz"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    greeting: set[str] = set()
    emotion: set[str] = set()
    scanned = 0
    t0 = time.time()
    with gzip.open(args.dump, "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if args.limit and i >= args.limit:
                break
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("lang_code") != "en":
                continue
            w = _WS.sub(" ", str(e.get("word") or "")).strip().lower()
            if not w or _HANGUL.search(w) or not _WORD_OK.match(w):
                continue
            scanned += 1
            pos = str(e.get("pos") or "")
            for s in e.get("senses") or []:
                for g in s.get("glosses") or []:
                    if _GREETING_GLOSS.search(g):
                        greeting.add(w)
                    # emotion words are adjectives/verbs/nouns describing a felt state
                    if pos in ("adj", "verb", "noun") and _EMOTION_GLOSS.search(g):
                        emotion.add(w)
    print(f"scanned {scanned} en headwords in {time.time()-t0:.0f}s")
    print(f"  greeting class: {len(greeting)}")
    print(f"  emotion  class: {len(emotion)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"greeting": sorted(greeting), "emotion": sorted(emotion)},
                              ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.name} (read-only sidecar, no store write)")
    for probe in ("howdy", "hiya", "cheers", "farewell", "knackered", "elated", "chuffed", "livid"):
        cls = [c for c, s in (("greeting", greeting), ("emotion", emotion)) if probe in s]
        print(f"  {probe:11} -> {cls or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
