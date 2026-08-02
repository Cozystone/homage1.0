# -*- coding: utf-8 -*-
"""OUTPUT-side register features — measured on what the realizer PRODUCES.

The fluency JUDGE (packages/fluency/verifier.py) already rates conversational prose ~0.95, so it is
UNINFORMATIVE for asking "did the GENERATOR become more conversational?". This module answers that
question directly, with explicit, interpretable surface statistics computed on the realizer's OUTPUT —
NOT the discriminator score:

  * function_word_ratio   — function words / all words (measured on the EXPANDED text so a contraction
                            counts as its two function words, not as a fused token).
  * contraction_rate      — contracted clitics / (clitics + still-contractible sites). 0 = nothing
                            contracted; ~1 = every contractible copula/aux collapsed.
  * contraction_count     — absolute number of contracted clitics (a raw count, register-independent).
  * discourse_marker_rate — fraction of sentences opening with an approved discourse marker.
  * discourse_marker_present — any approved discourse marker opens a sentence.
  * opener_variety        — distinct sentence-opener tokens / sentences (1.0 = every opener different;
                            low = the stiff "It … It … It …" parallel signature).
  * type_token_ratio      — distinct tokens / all tokens (lexical diversity).
  * mean_sentence_length  — words per sentence.

These are DESCRIPTIVE measurements, not a quality score and not a gate — they let a change to the
generator's register be reported as a per-feature delta, honestly, capped or not.
"""
from __future__ import annotations

import re
from typing import Any

from packages.fluency.conversational import (
    count_clitics,
    count_contractible_sites,
    expand_contractions,
)
from packages.fluency.register import APPROVED_DISCOURSE_MARKERS

# the LAD surface layer: closed-class function words (articles, pronouns, aux/copula, prepositions,
# conjunctions, particles). Doctrine-allowed; used ONLY to compute the function-word ratio.
FUNCTION_WORDS = frozenset({
    "a", "an", "the",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "who", "whom", "which", "whose", "what",
    "is", "am", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "do", "does", "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "in", "on", "at", "by", "for", "to", "of", "with", "from", "into", "onto", "over", "under",
    "above", "below", "between", "among", "through", "during", "before", "after", "about", "against",
    "without", "within", "across", "behind", "beyond", "near", "off", "out", "up", "down",
    "and", "or", "but", "so", "yet", "nor", "because", "although", "though", "while", "if", "unless",
    "since", "as", "than", "then", "when", "where", "why", "how",
    "not", "no", "also", "too", "very", "just", "only", "even", "still", "however", "there", "here",
})

_WORD = re.compile(r"[A-Za-z0-9']+")            # keep the apostrophe so "it's" is ONE surface token
_PLAIN = re.compile(r"[A-Za-z0-9]+")
_MARKERS_LOWER = frozenset(m.lower() for m in APPROVED_DISCOURSE_MARKERS)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _opener_token(sentence: str) -> str:
    m = _WORD.search(sentence or "")
    return m.group(0).lower() if m else ""


def function_word_ratio(text: str) -> float:
    """Function words / all words, measured on the EXPANDED surface so a contraction is counted as its
    constituent function words (it's -> it is), not penalized as a single opaque token."""
    toks = [w.lower() for w in _PLAIN.findall(expand_contractions(text or ""))]
    if not toks:
        return 0.0
    return sum(1 for w in toks if w in FUNCTION_WORDS) / len(toks)


def contraction_rate(text: str) -> float:
    """Contracted clitics / (clitics + still-contractible sites). 0.0 when nothing is (or could be)
    contracted; ~1.0 when every contractible copula/aux was collapsed."""
    c = count_clitics(text)
    s = count_contractible_sites(text)
    denom = c + s
    return c / denom if denom else 0.0


def contraction_count(text: str) -> int:
    return count_clitics(text)


def discourse_marker_rate(text: str) -> float:
    sents = _sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if _opener_token(s) in _MARKERS_LOWER) / len(sents)


def discourse_marker_present(text: str) -> bool:
    return discourse_marker_rate(text) > 0.0


def opener_variety(text: str) -> float:
    """Distinct sentence-opener tokens / number of sentences. Low = the stiff 'It … It … It …' parallel
    opener signature; higher = varied openers."""
    sents = _sentences(text)
    if not sents:
        return 0.0
    openers = [_opener_token(s) for s in sents]
    return len(set(openers)) / len(sents)


def type_token_ratio(text: str) -> float:
    toks = [w.lower() for w in _WORD.findall(text or "")]
    if not toks:
        return 0.0
    return len(set(toks)) / len(toks)


def mean_sentence_length(text: str) -> float:
    sents = _sentences(text)
    if not sents:
        return 0.0
    return sum(len(_WORD.findall(s)) for s in sents) / len(sents)


FEATURE_NAMES = (
    "function_word_ratio",
    "contraction_rate",
    "contraction_count",
    "discourse_marker_rate",
    "opener_variety",
    "type_token_ratio",
    "mean_sentence_length",
)


def register_features(text: str) -> dict[str, float]:
    """The full OUTPUT-side register feature vector for one realized answer."""
    return {
        "function_word_ratio": function_word_ratio(text),
        "contraction_rate": contraction_rate(text),
        "contraction_count": float(contraction_count(text)),
        "discourse_marker_rate": discourse_marker_rate(text),
        "opener_variety": opener_variety(text),
        "type_token_ratio": type_token_ratio(text),
        "mean_sentence_length": mean_sentence_length(text),
    }


def mean_features(texts: list[str]) -> dict[str, float]:
    """Mean of each feature over a set of realized answers (empty answers skipped)."""
    rows = [register_features(t) for t in texts if (t or "").strip()]
    if not rows:
        return {k: 0.0 for k in FEATURE_NAMES}
    return {k: sum(r[k] for r in rows) / len(rows) for k in FEATURE_NAMES}


def feature_delta(before_texts: list[str], after_texts: list[str]) -> dict[str, dict[str, float]]:
    """Per-feature {before, after, delta} between two sets of realized answers (paired by set means)."""
    b = mean_features(before_texts)
    a = mean_features(after_texts)
    return {k: {"before": b[k], "after": a[k], "delta": a[k] - b[k]} for k in FEATURE_NAMES}


# ── OUTPUT syntactic-STRUCTURE features — measured on the CLAUSE PLANNER's output ──────────────────
# The register features above describe the conversational SURFACE (contractions, markers). These
# describe clause STRUCTURE: how often a sentence combines multiple facts (apposition / coordination /
# relative subordination), how FEW sentences an answer takes (clause-count reduction), and how VARIED
# their lengths are. They are SURFACE heuristics — marker/shape detection, not a real parse — so they
# are honest DESCRIPTIONS of the output, not a quality score. The combining planner should raise the
# combination/subordination rates and drop the sentence count while holding TTR flat-or-up.

def _has_appositive(sentence: str) -> bool:
    """A subject-appositive shape: a comma immediately after the first (subject) word, then a CLOSING
    comma before the main verb — "Kettle, a vessel made of steel, can …". A flat "Kettle is a vessel,
    made of steel." is NOT an appositive: its first comma follows "vessel", not the subject word."""
    m = re.match(r"[A-Z][\w'-]*,\s", sentence or "")
    return bool(m) and "," in (sentence[m.end():] if m else "")


def _has_relative(sentence: str) -> bool:
    """A relative clause: a 'that'/'which'/'who' followed by a verb/aux — "… rodents that can climb".
    The approved discourse connective 'which is why' (a closed-class connective, not a relativizer) is
    masked first so it is not miscounted as subordination."""
    s = re.sub(r"\bwhich\s+is\s+why\b", " ", sentence or "", flags=re.I)
    return bool(re.search(r"\b(?:that|which|who)\s+(?:can|could|will|would|is|are|was|were|has|have|had)\b",
                          s, re.I))


def _has_coordination(sentence: str) -> bool:
    """A coordinating 'and' joining predicates/phrases within one sentence (VP or NP coordination)."""
    return bool(re.search(r"\s+and\s+", sentence or "", re.I))


def sentence_count(text: str) -> float:
    return float(len(_sentences(text)))


def combination_rate(text: str) -> float:
    """Fraction of sentences that COMBINE ≥2 facts — appositive, relative, or coordinating 'and'."""
    sents = _sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if _has_appositive(s) or _has_relative(s) or _has_coordination(s)) / len(sents)


def subordination_rate(text: str) -> float:
    """Fraction of sentences carrying a DEPENDENT structure (appositive or relative) — the re-packaging a
    flat one-clause-per-fact planner cannot produce (coordination alone is not subordination)."""
    sents = _sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if _has_appositive(s) or _has_relative(s)) / len(sents)


def appositive_rate(text: str) -> float:
    sents = _sentences(text)
    return sum(1 for s in sents if _has_appositive(s)) / len(sents) if sents else 0.0


def relative_clause_rate(text: str) -> float:
    sents = _sentences(text)
    return sum(1 for s in sents if _has_relative(s)) / len(sents) if sents else 0.0


def coordination_rate(text: str) -> float:
    sents = _sentences(text)
    return sum(1 for s in sents if _has_coordination(s)) / len(sents) if sents else 0.0


def sentence_length_cv(text: str) -> float:
    """Coefficient of variation (stdev/mean) of per-sentence word counts — rhythm variety. A flat
    'It can X. It has Y.' answer has near-uniform short sentences (low CV); a combined answer mixes a
    long head with a short continuation (higher CV)."""
    sents = _sentences(text)
    lens = [len(_WORD.findall(s)) for s in sents]
    if len(lens) < 2:
        return 0.0
    mean = sum(lens) / len(lens)
    if mean <= 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    return (var ** 0.5) / mean


SYNTAX_FEATURE_NAMES = (
    "sentence_count",
    "combination_rate",
    "subordination_rate",
    "appositive_rate",
    "relative_clause_rate",
    "coordination_rate",
    "type_token_ratio",
    "mean_sentence_length",
    "sentence_length_cv",
)


def syntactic_features(text: str) -> dict[str, float]:
    """The OUTPUT syntactic-structure feature vector for one realized answer."""
    return {
        "sentence_count": sentence_count(text),
        "combination_rate": combination_rate(text),
        "subordination_rate": subordination_rate(text),
        "appositive_rate": appositive_rate(text),
        "relative_clause_rate": relative_clause_rate(text),
        "coordination_rate": coordination_rate(text),
        "type_token_ratio": type_token_ratio(text),
        "mean_sentence_length": mean_sentence_length(text),
        "sentence_length_cv": sentence_length_cv(text),
    }


def mean_syntactic_features(texts: list[str]) -> dict[str, float]:
    rows = [syntactic_features(t) for t in texts if (t or "").strip()]
    if not rows:
        return {k: 0.0 for k in SYNTAX_FEATURE_NAMES}
    return {k: sum(r[k] for r in rows) / len(rows) for k in SYNTAX_FEATURE_NAMES}


def syntactic_feature_delta(before_texts: list[str], after_texts: list[str]) -> dict[str, dict[str, float]]:
    """Per-feature {before, after, delta} of the syntactic-structure features between two answer sets."""
    b = mean_syntactic_features(before_texts)
    a = mean_syntactic_features(after_texts)
    return {k: {"before": b[k], "after": a[k], "delta": a[k] - b[k]} for k in SYNTAX_FEATURE_NAMES}
