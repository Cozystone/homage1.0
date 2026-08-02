# -*- coding: utf-8 -*-
"""Deterministic continuity grader — no LLM judge, no fabricated recall.

The official MemAware metric asks a GPT-5.1 judge whether the agent's RESPONSE proactively
surfaced the labeled personal detail. We cannot run that judge (No-LLM; no external judge). So we
grade the layer directly upstream of any response: did the memory organ SURFACE the correct gold
episode in its top-k recall?

    continuity(surfaced_unit_ids, gold_unit_ids) = 1  iff the two sets intersect, else 0.

This is anti-fabrication by construction: a point requires the retrieved item's PROVENANCE (its
source session id, or its day-file id for the day-granularity baseline) to be one of the labeled
gold ids. A retriever that returns a wrong-but-lexically-similar episode scores 0; a retriever
that surfaces nothing scores 0; there is no text-similarity or "the model claimed it remembered"
backdoor. A hallucinated recall therefore cannot earn a point.

`answer_grounded` is a SECONDARY data-integrity check (does the surfaced gold text actually contain
the labeled answer tokens) — reported as a sanity number, never used to award continuity.
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "is", "are", "was", "were",
         "be", "by", "as", "at", "it", "its", "this", "that", "with", "from", "user", "was"}


def continuity(surfaced_unit_ids, gold_unit_ids) -> int:
    """1 if any surfaced unit's provenance is a gold unit, else 0. The whole metric."""
    return 1 if (set(surfaced_unit_ids) & set(gold_unit_ids)) else 0


def hit_rank(surfaced_unit_ids, gold_unit_ids):
    """Rank (1-based) of the first surfaced gold unit, or None if the gold was never surfaced.
    Lets us report continuity@1 (surfaced as the TOP memory) separately from continuity@k."""
    gold = set(gold_unit_ids)
    for i, uid in enumerate(surfaced_unit_ids, start=1):
        if uid in gold:
            return i
    return None


def _content_tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(str(text).lower()) if len(w) > 1 and w not in _STOP}


def answer_grounded(surfaced_texts, answer: str, min_overlap: float = 0.6) -> bool:
    """SANITY ONLY (not scored): does any surfaced text actually contain the answer's content tokens?
    Confirms the gold episode really holds the fact — guards the dataset, not the model."""
    ans = _content_tokens(answer)
    if not ans:
        return False
    for t in surfaced_texts:
        toks = _content_tokens(t)
        if len(ans & toks) / len(ans) >= min_overlap:
            return True
    return False
