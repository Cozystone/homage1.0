"""Data-driven subword units — how LLMs actually learn language, applied to ATANOR.

Modern LLMs never receive hand-written morphology rules. They learn their units with Byte-Pair
Encoding / SentencePiece: start from characters and iteratively MERGE the most frequent adjacent
pair. It is language-agnostic (one algorithm for Korean, English, anything) and — the point for
ATANOR — for an agglutinative language it DISCOVERS the morpheme boundaries from frequency: a
stem whose characters always co-occur (··) merges into one unit, while a particle that
attaches to many different stems (//) stays a separate token. So the / boundaries we
used to hand-code fall out of the data on their own.

This is the data-derived front-end that concentrates relationships onto one node (·
→ + /) — the density the surface graph needs — without a rule table.

Reference: BPE (Sennrich et al. 2016), SentencePiece (Kudo & Richardson 2018).
Deterministic, no LLM, no neural net — pure frequency merging.
"""
from __future__ import annotations

from collections import Counter

_BOW = "▁"  # ▁ — SentencePiece-style word-start marker (handles no-space CJK uniformly)

Pair = tuple[str, str]


def _words(line: str) -> list[str]:
    return [w for w in str(line or "").split() if w]


def _merge_symbols(symbols: tuple[str, ...], pair: Pair) -> tuple[str, ...]:
    a, b = pair
    merged = a + b
    out: list[str] = []
    i = 0
    while i < len(symbols):
        if i < len(symbols) - 1 and symbols[i] == a and symbols[i + 1] == b:
            out.append(merged)
            i += 2
        else:
            out.append(symbols[i])
            i += 1
    return tuple(out)


def learn_bpe(corpus: list[str] | tuple[str, ...], *, num_merges: int = 200, min_freq: int = 2) -> list[Pair]:
    """Learn an ORDERED list of merges from a corpus — the whole 'training'. Each word starts as
    ▁ + its characters; the most frequent adjacent pair is merged, repeatedly."""
    vocab: Counter[tuple[str, ...]] = Counter()
    for line in corpus:
        for word in _words(line):
            vocab[tuple(_BOW + word)] += 1
    merges: list[Pair] = []
    for _ in range(max(0, num_merges)):
        pairs: Counter[Pair] = Counter()
        for word, freq in vocab.items():
            for a, b in zip(word, word[1:]):
                pairs[(a, b)] += freq
        if not pairs:
            break
        best, count = pairs.most_common(1)[0]
        if count < min_freq:
            break  # nothing recurs → stop (don't memorize one-offs)
        merges.append(best)
        vocab = Counter({_merge_symbols(w, best): f for w, f in vocab.items()})
    return merges


def tokenize(text: str, merges: list[Pair]) -> list[str]:
    """Segment text into learned subword units by applying the merges in learned-rank order."""
    rank = {pair: i for i, pair in enumerate(merges)}
    out: list[str] = []
    for word in _words(text):
        symbols = tuple(_BOW + word)
        while len(symbols) > 1:
            best: Pair | None = None
            best_rank = len(rank) + 1
            for a, b in zip(symbols, symbols[1:]):
                r = rank.get((a, b))
                if r is not None and r < best_rank:
                    best, best_rank = (a, b), r
            if best is None:
                break
            symbols = _merge_symbols(symbols, best)
        out.extend(symbols)
    return out


def pretty(tokens: list[str]) -> list[str]:
    """Drop the ▁ marker for display ('▁' → '')."""
    return [t.replace(_BOW, "") for t in tokens]
