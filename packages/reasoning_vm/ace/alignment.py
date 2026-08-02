# -*- coding: utf-8 -*-
"""Interactive-alignment priming for the realizer (Pickering & Garrod 2004, implemented explicitly).

Human dialogue feels like dialogue because speakers automatically CONVERGE: they reuse each other's
words and constructions (lexical/syntactic priming, six levels, correlated with task success). LLMs
learn this implicitly through attention over the dialogue history; ATANOR, being neuro-symbolic,
implements it as an explicit, inspectable mechanism — no training required:

  1. extract the interlocutor's recent CONTENT words (stopwords carry no alignment signal),
  2. map them to realizer token ids (with leading-space BPE variants),
  3. hand them to Realizer.generate(logit_bias=...) as small positive deltas, recency-weighted.

The bias is deliberately small (default +1.5): alignment leans word CHOICE toward the shared
vocabulary without overriding the grammar the LM provides. Doctrine-safe: priming shapes STYLE, never
facts — grounding still comes only from bones, and the receipt gate still decides whether to speak.

Research: docs/ATANOR_human_speech_production_research.md (P3/A1).
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")
_STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "by", "for", "with", "and", "or", "but",
         "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "have", "has",
         "had", "it", "its", "this", "that", "these", "those", "i", "you", "he", "she", "we",
         "they", "me", "him", "her", "us", "them", "my", "your", "his", "their", "our", "what",
         "which", "who", "how", "when", "where", "why", "not", "no", "yes", "so", "as", "if",
         "then", "than", "too", "very", "can", "could", "will", "would", "should", "about"}


def extract_prime_words(history: list[str], max_turns: int = 3, max_words: int = 24) -> list[str]:
    """The interlocutor's recent content words, most-recent turn first (recency drives priming
    strength in humans too). Lowercased, deduplicated, stopword-free."""
    seen: set[str] = set()
    out: list[str] = []
    for turn in reversed(history[-max_turns:]):
        for w in _WORD.findall(turn or ""):
            lw = w.lower()
            if lw in _STOP or len(lw) < 3 or lw in seen:
                continue
            seen.add(lw)
            out.append(lw)
            if len(out) >= max_words:
                return out
    return out


def prime_bias(tok, history: list[str], strength: float = 1.5,
               max_turns: int = 3, max_words: int = 24) -> dict[int, float]:
    """Build the logit-bias dict for Realizer.generate. Each prime word contributes its BPE token ids
    (bare + leading-space variant, first sub-token only — enough to tilt selection), recency-decayed
    so the latest turn primes hardest, exactly as measured in humans."""
    words = extract_prime_words(history, max_turns, max_words)
    bias: dict[int, float] = {}
    n = max(1, len(words))
    for rank, w in enumerate(words):
        delta = strength * (1.0 - 0.5 * rank / n)          # linear recency decay, floor = strength/2
        for form in (w, " " + w, w.capitalize(), " " + w.capitalize()):
            ids = tok.encode(form).ids
            if ids:
                t = ids[0]
                bias[t] = max(bias.get(t, 0.0), delta)      # max, not sum — one word, one vote
    return bias
