# -*- coding: utf-8 -*-
"""Tier B / B1 — DrQA-style question-passage MATCH features (the L1 rung of the span ladder).

Measured starting point: E9's span head reached F1 0.568 with the hand-feature channel RETIRED
(data2 zeroed `feats`, model2 ignores it). The external anchor is that GloVe+attention models with
exactly these features reach 77-79 F1 on SQuAD (BiDAF/DrQA) WITHOUT a pretrained transformer, so
0.75 is a from-scratch-attained region and the gap is engineering, not a wall.

This module computes, for each PASSAGE token, whether/how it aligns with the QUESTION — the single
most informative signal for extractive QA (the answer is near tokens that echo the question):

  exact      the passage token appears verbatim in the question
  lower      case-insensitive match
  stem       conservative stem match (trailing s / ed / ing / ies) — "runs"~"run", "cities"~"city"
  tfidf      the idf weight of the matched question token (rare matches matter more than "the")
  is_cap     the token is capitalised (proper-noun / entity signal)
  is_num     the token is a number or a 3-4 digit year
  pos        normalised position in the passage

Pure and dependency-light (an optional idf map sharpens `tfidf`; absent, it falls back to 1.0 on
match). This is the channel data2 must repopulate and model2 must project+consume in W1; here it is
built and unit-tested on its own so the feature is correct before any GPU time is spent on it.
"""
from __future__ import annotations

import math
import re
from collections import Counter

FEATURE_NAMES = ["exact", "lower", "stem", "tfidf", "is_cap", "is_num", "pos"]
NFEAT = len(FEATURE_NAMES)

_WORD = re.compile(r"[A-Za-z0-9]+")
_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"}
def tokenize(text: str) -> list[str]:
    return _WORD.findall(text or "")


def _stem(w: str) -> str:
    """Conservative suffix stripping — enough to bridge run/runs/running and city/cities, not a full
    stemmer (over-stemming creates false matches that hurt precision). Critically, '-es' is stripped
    only after a sibilant (boxes->box, dishes->dish); otherwise just the '-s' comes off so 'lives'
    stems to 'live', not 'liv'."""
    lw = w.lower()
    if len(lw) <= 3:
        return lw
    if lw.endswith("ies") and len(lw) > 4:
        return lw[:-3] + "y"
    if lw.endswith("ing") and len(lw) > 5:
        return lw[:-3]
    if lw.endswith("ed") and len(lw) > 4:
        return lw[:-2]
    if lw.endswith("es") and (lw.endswith(("ches", "shes")) or lw[-3:-2] in "sxz"):
        return lw[:-2]                                  # boxes->box, dishes->dish
    if lw.endswith("s") and not lw.endswith("ss"):
        return lw[:-1]                                  # lives->live, runs->run
    return lw


def build_idf(passages: list[str]) -> dict[str, float]:
    """Small document-frequency idf over a passage corpus, for weighting question matches. Rare
    question words (entities, terms) carry far more answer-locating signal than 'the' or 'of'."""
    n = max(1, len(passages))
    df: Counter = Counter()
    for p in passages:
        for w in set(t.lower() for t in tokenize(p)):
            df[w] += 1
    return {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}


def passage_match_features(question: str, passage: str,
                           idf: dict[str, float] | None = None) -> list[list[float]]:
    """Return one NFEAT-vector per passage token, aligning it to the question."""
    q_tokens = tokenize(question)
    q_lower = {w.lower() for w in q_tokens}
    q_stem = {_stem(w) for w in q_tokens}
    q_exact = set(q_tokens)
    p_tokens = tokenize(passage)
    n = max(1, len(p_tokens))
    max_idf = max(idf.values()) if idf else 1.0
    out: list[list[float]] = []
    for i, w in enumerate(p_tokens):
        lw = w.lower()
        exact = 1.0 if w in q_exact else 0.0
        lower = 1.0 if lw in q_lower else 0.0
        stem = 1.0 if _stem(w) in q_stem else 0.0
        if idf is not None and lower:
            tfidf = min(1.0, idf.get(lw, 0.0) / max(1e-6, max_idf))
        else:
            tfidf = lower                     # no idf map -> presence acts as the weight
        is_cap = 1.0 if w[:1].isupper() else 0.0
        is_num = 1.0 if (w.isdigit() or re.fullmatch(r"\d{3,4}", w) or lw in _MONTHS) else 0.0
        pos = i / n
        out.append([exact, lower, stem, tfidf, is_cap, is_num, pos])
    return out


def overlap_score(question: str, passage: str, idf: dict[str, float] | None = None) -> float:
    """A single idf-weighted question-overlap score for a passage — the answerless-baseline signal a
    retriever/reranker can use before the span head runs. High = the passage echoes the question."""
    feats = passage_match_features(question, passage, idf)
    if not feats:
        return 0.0
    return sum(f[3] for f in feats) / len(feats)      # mean tfidf-match over passage tokens
