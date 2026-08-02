# -*- coding: utf-8 -*-
"""Order miner -- extracts directed event-order observations from real text.

The ONLY symbolic anchors are closed-class temporal connectives (grammar, like ISO date parsing):
"A before B" / "after A, B" / "A then B" / "A until B" / "once A, B" / "A prior to B" /
"A, subsequently B" / "A followed by B". Which OPEN-CLASS words precede which is never authored
here -- it is emitted as raw directed observations (a -> b = "a happened before b") for the
precedence field to learn from. See docs/ATANOR_temporal_causal_physics.md.
"""
from __future__ import annotations

import bz2
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

# closed-class connectives; each maps a sentence split into (earlier-side, later-side).
# "X before Y"  -> X earlier   |   "X after Y" -> Y earlier (subordinate clause happened first)
_BEFORE = re.compile(r"^(?P<a>.+?)\b(?:before|prior to|until)\b(?P<b>.+)$", re.IGNORECASE)
_AFTER = re.compile(r"^(?P<b>.+?)\b(?:after|once|as soon as)\b(?P<a>.+)$", re.IGNORECASE)
_THEN = re.compile(r"^(?P<a>.+?)\b(?:and then|then|followed by|subsequently|afterwards?)\b(?P<b>.+)$",
                   re.IGNORECASE)

# function-word stoplist: closed-class grammar, not world knowledge (pronouns/aux/det/prep).
_STOP = {"the", "a", "an", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
         "them", "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
         "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "have",
         "has", "had", "will", "would", "can", "could", "shall", "should", "may", "might", "must",
         "to", "of", "in", "on", "at", "by", "for", "with", "from", "into", "onto", "about",
         "and", "or", "but", "not", "no", "so", "if", "as", "than", "too", "very", "just",
         "there", "here", "when", "while", "who", "what", "which", "why", "how", "all", "some",
         "any", "each", "every", "both", "few", "more", "most", "other", "such", "only", "own",
         "same", "s", "t", "don", "now", "up", "down", "out", "off", "over", "under", "again",
         "get", "got", "go", "went", "gone", "going", "come", "came", "let", "lets", "please",
         "one", "two", "three", "first", "last", "next", "new", "old", "long", "time", "day",
         "year", "week", "month", "hour", "minute", "moment", "morning", "evening", "night",
         "today", "tomorrow", "yesterday", "soon", "later", "ago", "never", "always", "often",
         "sometimes", "usually", "still", "yet", "even", "also", "back", "away", "home", "want",
         "wanted", "like", "liked", "need", "needed", "think", "thought", "know", "knew", "say",
         "said", "tell", "told", "ask", "asked", "make", "made", "take", "took", "give", "gave",
         "see", "saw", "look", "looked", "good", "bad", "well", "way", "thing", "things", "man",
         "woman", "people", "person", "something", "anything", "nothing", "everything", "left"}

_WORD = re.compile(r"[a-z]{3,}")


def _event_tokens(clause: str, side: str) -> list[str]:
    """Candidate event tokens from a clause: content words nearest the connective (the clause edge
    facing it). Noisy per-sentence; correct at corpus scale."""
    words = [w for w in _WORD.findall(clause.lower()) if w not in _STOP]
    if not words:
        return []
    # the words adjacent to the connective carry the event most often
    return words[-2:] if side == "a_left" else words[:2]


def sentence_pairs(sentence: str) -> list[tuple[str, str]]:
    """Directed (earlier, later) token pairs mined from one sentence, or []."""
    return [(a, b) for a, b, _ in sentence_pairs_ctx(sentence)]


def sentence_pairs_ctx(sentence: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """Directed (earlier, later, context) triples. Context = up to 4 content words of the SAME
    sentence that are not the event tokens themselves -- the sense anchor (e.g. 'restored' next to
    'telemetry' is a different sense than next to 'castle'). Sense-awareness lives here, in data,
    never in an authored sense inventory."""
    s = sentence.strip()
    if not (8 < len(s) < 400):
        return []
    for rx, a_side in ((_BEFORE, "left"), (_AFTER, "right"), (_THEN, "left")):
        m = rx.match(s)
        if not m:
            continue
        a_cl, b_cl = m.group("a"), m.group("b")
        a_toks = _event_tokens(a_cl, "a_left" if a_side == "left" else "b_right")
        b_toks = _event_tokens(b_cl, "b_right" if a_side == "left" else "a_left")
        ev = set(a_toks) | set(b_toks)
        ctx = tuple(w for w in _WORD.findall(s.lower())
                    if w not in _STOP and w not in ev)[:4]
        return [(a, b, ctx) for a in a_toks for b in b_toks if a != b]
    return []


def iter_corpus_lines(path: Path) -> Iterator[str]:
    """Stream lines from .txt / .tsv(.bz2) (tatoeba: id<TAB>lang<TAB>text) / .xml(.bz2) (wiki)."""
    opener = bz2.open if path.suffix == ".bz2" else open
    stem = path.name.lower()
    with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "\t" in line and (".tsv" in stem or "sentences" in stem):
                parts = line.rstrip("\n").split("\t")
                yield parts[-1]
            elif ".xml" in stem:
                # crude wiki text: skip markup-heavy lines, split into sentences
                if "<" in line or "{{" in line or "[[" in line[:2]:
                    continue
                for sent in re.split(r"(?<=[.!?])\s+", line.strip()):
                    yield sent
            else:
                yield line.strip()


def mine(paths: Iterable[Path], max_lines: int | None = None) -> Counter:
    """Mine directed order observations. Returns Counter[(earlier, later)] -> count."""
    counts: Counter = Counter()
    n = 0
    for p in paths:
        for line in iter_corpus_lines(p):
            n += 1
            if max_lines and n > max_lines:
                return counts
            for pair in sentence_pairs(line):
                counts[pair] += 1
    return counts


def mine_ctx(paths: Iterable[Path], max_lines: int | None = None) -> tuple[Counter, Counter]:
    """Sense-aware mining: returns (pair_counts[(a,b)], ctx_counts[(ctx,a,b)]) where ctx is one
    content word from the observing sentence -- the pair's direction WITHIN that context."""
    pair_counts: Counter = Counter()
    ctx_counts: Counter = Counter()
    n = 0
    for p in paths:
        for line in iter_corpus_lines(p):
            n += 1
            if max_lines and n > max_lines:
                return pair_counts, ctx_counts
            for a, b, ctx in sentence_pairs_ctx(line):
                pair_counts[(a, b)] += 1
                for c in ctx:
                    ctx_counts[(c, a, b)] += 1
    return pair_counts, ctx_counts
