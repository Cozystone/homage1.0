# -*- coding: utf-8 -*-
"""Lexicon cartridge lane — offline dictionary answers from the Kaikki knowledge cartridge.

The cartridge (data/graph_scale/kg_triples) holds ~2M curated dictionary triples
(defined_as / is_a / alias) extracted VERBATIM from Wiktionary's structured data —
no generation, so surfacing them cannot fabricate. This lane answers definition-style
questions when the learned graph has no coverage: it sits AFTER graph_grounded
(verified learning outranks a dictionary) and BEFORE web (offline beats network).

Scope is deliberately narrow (owner: AI — ):
 - exact-subject match only (plus a trailing-josa-stripped retry) — no fuzzy guessing
 - defined_as first, then is_a; glosses in the asker's language preferred
 - realized as one clean sentence with batchim-correct josa, never a raw triple dump
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_STORE = None            # lazy TripleStore singleton (index builds on first lookup)
_STORE_PATH: Path | None = None

_HANGUL = re.compile(r"[가-힣]")
# interrogative / filler tokens that are never the thing being defined
_STOP = {"뭐야", "뭐지", "무엇", "무엇인가", "뜻", "의미", "설명", "알려줘", "정의",
         "what", "is", "the", "a", "an", "of", "mean", "means", "meaning", "define"}
_JOSA_TAIL = re.compile(r"(은|는|이|가|을|를|의|이란|란|라는|이라는|이야|야|이니|니)$")
# English function words. Wiktionary has entries for grammatical phrases like "do you", so once we
# started forming n-grams a purely grammatical span could win the lookup: "What do you think about
# music?" matched 'do you' → "Used other than figuratively or idiomatically: see do, you."
# A candidate must carry at least one CONTENT word — grammar is how a question is asked, never the
# thing it asks about. English-only by construction: Korean keys carry no ASCII, so they never match
# this set and the Korean lane is untouched.
_FUNCTION_WORDS = {
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "this", "that", "these", "those", "there", "here", "who", "whom",
    "whose", "which", "what", "when", "where", "why", "how", "do", "does", "did", "done", "be",
    "am", "is", "are", "was", "were", "been", "being", "have", "has", "had", "can", "could", "will",
    "would", "shall", "should", "may", "might", "must", "and", "or", "but", "if", "then", "than",
    "so", "as", "at", "by", "for", "from", "in", "into", "on", "onto", "to", "with", "about", "of",
    "off", "out", "up", "down", "over", "under", "again", "not", "no", "yes", "the", "a", "an",
    "some", "any", "all", "both", "each", "few", "more", "most", "other", "such", "only", "own",
    "same", "too", "very", "just", "now", "please", "tell", "think", "know",
}


def _has_content(key: str) -> bool:
    toks = re.findall(r"[0-9A-Za-z가-힣]+", key)
    return any(t.lower() not in _FUNCTION_WORDS for t in toks) if toks else False
# meta-glosses that are cross-references, not definitions ("alternative spelling of X").
# INFLECTIONS belong here too: "third-person singular simple present indicative of reenable" tells
# you how a word is conjugated, not what a thing is. Measured 2026-07-17, once the vulgar sense was
# gated: "What does the Eiffel Tower look like?" → "Eiffel Tower — third-person singular simple
# present indicative of reenable" — which is also a mis-keyed cartridge row (a landmark is not a
# verb form), so surfacing any form-of gloss is doubly wrong.
_META_GLOSS = re.compile(
    r"^(alternative (spelling|form) of|misspelling of|synonym of|abbreviation of|"
    r"initialism of|acronym of|short for|romanization of|obsolete "
    r"|(?:.*\b)?(?:singular|plural|past|present|future|comparative|superlative|gerund|"
    r"participle|indicative|subjunctive|imperative|infinitive|inflection|conjugation)\b"
    r".*\bof\s+\S)", re.IGNORECASE)
# EXPLICIT SLANG SENSES. Wiktionary documents vulgar slang without a machine-readable label in this
# cartridge, so a landmark can carry a sexual sense next to the real one. Measured 2026-07-17:
# "What does the Eiffel Tower look like?" answered "Eiffel Tower — A spit roast with the two
# penetrating partners high-fiving." Surfacing that unasked is a safety failure, not a fluency one.
# Dropping the GLOSS (not the entry) keeps the ordinary sense answerable. Descriptive anatomy in a
# genuine definition is not the target — the filter is deliberately narrow to sexual-act slang.
_VULGAR_GLOSS = re.compile(
    r"\b(spit[- ]roast|penetrat(?:ing|ion)|blowjob|handjob|rimming|felching|"
    r"cum|jizz|semen\s+on|anal\s+sex|oral\s+sex|masturbat|ejaculat|"
    r"genitals?\s+(?:of|onto)|penis\s+(?:into|in\s+the)|vagina\s+(?:into|during)|"
    r"sexual\s+(?:act|intercourse|position|practice)|having\s+sex|during\s+sex)\b",
    re.IGNORECASE)


def _gloss_ok(gloss: str) -> bool:
    return not _META_GLOSS.match(gloss) and not _VULGAR_GLOSS.search(gloss)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _store():
    global _STORE, _STORE_PATH
    if _STORE is None:
        from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
        from packages.graph_scale.triple_store import TripleStore

        _STORE_PATH = SHIPPED_GRAPH_ROOT
        _STORE = TripleStore(_STORE_PATH)
    return _STORE


def available() -> bool:
    if os.getenv("ATANOR_LEXICON_OFF") == "1":
        return False
    try:
        return len(_store()) > 0
    except Exception:
        return False


# English indefinite article by SOUND, not spelling: the vowel-letter rule alone yields "a object"
# (measured) one way and "an unicorn"/"a hour" the other. These are the exception classes that
# actually fire on dictionary categories; anything else follows the vowel-letter rule.
_AN_EXCEPTIONS = re.compile(r"^(hour|honest|honou?r|heir)", re.IGNORECASE)   # silent h → an
_A_EXCEPTIONS = re.compile(r"^(uni|use|user|usual|euro|ewe|one|once)", re.IGNORECASE)  # /j/,/w/ → a


def _article(word: str) -> str:
    w = word.strip()
    if not w:
        return "a"
    if _AN_EXCEPTIONS.match(w):
        return "an"
    if _A_EXCEPTIONS.match(w):
        return "a"
    return "an" if w[0].lower() in "aeiou" else "a"


def _gloss_lang_ok(gloss: str, language: str) -> bool:
    has_ko = bool(_HANGUL.search(gloss))
    return has_ko if language == "ko" else not has_ko


def _candidates(entity: str) -> list[str]:
    """Ordered lookup keys from a possibly-messy entity/query — the subject extractor
 is inconsistent ('' vs ' '), so we try the whole thing, then each
 content token (question words dropped, trailing josa stripped), longest first."""
    entity = entity.strip()
    seen: list[str] = []

    def _add(k: str) -> None:
        k = k.strip()
        if k and k not in seen and k.lower() not in _STOP and _has_content(k):
            seen.append(k)

    _add(entity)
    _add(_JOSA_TAIL.sub("", entity))
    toks = [t for t in re.findall(r"[0-9A-Za-z가-힣]+", entity) if t.lower() not in _STOP]
    # CASE IS MEANING in English, so do NOT try case variants of the asker's word. Tried and
    # reverted 2026-07-17: 'coffee' holds only ConceptNet relations while 'Coffee' holds four
    # defined_as, which looked like a free coverage win — until the glosses turned out to be
    # PROPER NOUNS. 'Coffee' is a surname; 'Tea' is a city in South Dakota; 'Money' is a community
    # in Mississippi. This cartridge encodes the common/proper distinction in the capital, so
    # up-casing a common noun silently swaps the referent. Preserve the asker's case.
    # ADJACENT PHRASES BEFORE BARE WORDS: an English multiword concept is ONE entity, and its bare
    # head/modifier defines something else entirely. Measured: "What is a black hole?" tried the
    # longest single token first ('black') and answered "black — abscence of color" — the phrase
    # 'black hole' was never even formed. Contiguous n-grams (longest first) fix the whole class
    # (polar bear, machine learning, climate change…). Single tokens remain as fallbacks.
    for width in range(min(4, len(toks)), 1, -1):
        for start in range(len(toks) - width + 1):
            _add(" ".join(toks[start:start + width]))
    for t in sorted(toks, key=len, reverse=True):
        _add(t)
        _add(_JOSA_TAIL.sub("", t))
    return seen


def _facts(entity: str) -> list[tuple[str, str, str]]:
    """First candidate with rows. Candidates are ordered longest-phrase-first, and that ORDER is
    the precision guarantee — do not re-rank by "has a definition".

    Tried and reverted 2026-07-17: preferring any candidate that carries a defined_as row sounds
    strictly better (it would rescue 'coffee', whose lowercase entry holds only ConceptNet
    relations). Measured, it resurrects head truncation — 'Eiffel Tower' has no gloss but the bare
    'Eiffel' has one, so the phrase lost to "Eiffel — A surname from French." A definition for the
    wrong referent is worse than an honest is_a for the right one.
    """
    st = _store()
    for key in _candidates(entity):
        if len(key) < 2:
            continue
        # LIMIT MUST NOT TRUNCATE THE DEFINITIONAL PREDICATES. The row limit was 24 and
        # located_in is by far the most numerous ConceptNet relation, so a well-connected subject
        # spent the whole budget on locations and lost its is_a. Measured 2026-07-17: 'coffee' has
        # 19 located_in + 2 has_a + 2 has_property = 23 rows before its 6 is_a (incl. 'beverage')
        # ever appear, so the lane answered "nothing grounded on coffee" while `coffee is_a
        # beverage` sat in the store. 'tea' escaped only by having 7 locations instead of 19.
        # I twice reported this as a data gap; it was this truncation.
        rows = list(st.facts_about(key, limit=96))
        if rows:
            return rows
    return []


def senses(entity: str, language: str = "ko", limit: int = 4) -> list[str]:
    """The DISTINCT readings of `entity` in the asker's language ([] = unknown / single reading).

 Enumerating senses is the doctrine (sense=, not alias=): a polysemous term has no
 'right' gloss to assert. Measured: the cartridge lists Python's earth-dragon-of-Delphi sense
 first, so any lane that takes defs[0] answers a question about the programming language with
 Greek mythology. A caller that knows the term is polysemous can ask which reading is meant
 instead of guessing — which is what a careful person does.
 """
    entity = (entity or "").strip()
    if not entity or len(entity) > 40 or not available():
        return []
    try:
        rows = _facts(entity)
    except Exception:
        return []
    out: list[str] = []
    for s, p, o in rows:
        if p != "defined_as" or not _gloss_ok(o) or not _gloss_lang_ok(o, language):
            continue
        norm = re.sub(r"[^0-9a-z가-힣 ]", "", o.lower()).strip()
        if norm and not any(norm[:24] == re.sub(r"[^0-9a-z가-힣 ]", "", x.lower()).strip()[:24]
                            for x in out):
            out.append(o.rstrip("."))
        if len(out) >= limit:
            break
    return out


def lookup(entity: str, language: str = "ko") -> dict[str, Any] | None:
    """One grounded dictionary sentence for `entity`, or None (never a guess)."""
    entity = (entity or "").strip()
    if not entity or len(entity) > 40 or not available():
        return None
    try:
        rows = _facts(entity)
    except Exception:
        return None
    if not rows:
        return None

    subject = rows[0][0]
    defs = [o for s, p, o in rows if p == "defined_as" and _gloss_ok(o)]
    kinds = [o for s, p, o in rows if p == "is_a"]

    if language == "ko":
        # prefer a Korean gloss; an English one is still usable (framed as dictionary data below)
        gloss = next((g for g in defs if _gloss_lang_ok(g, language)), defs[0] if defs else None)
        kind = kinds[0] if kinds else None
    else:
        # NO CROSS-SCRIPT FALLBACK: a Korean gloss is a translation of the word, not a definition of
        # the thing, so surfacing it answers a different question in the wrong language. Measured:

        # (None) hands the question to the next lane, which is the honest outcome.
        gloss = next((g for g in defs if _gloss_lang_ok(g, language)), None)
        kind = next((k for k in kinds if _gloss_lang_ok(k, language)), None)
    if gloss is None and kind is None:
        return None

    # target): the gloss only expands the name with no descriptive content. Defer (None) so a richer
    # curated definition can answer — but only when there is no descriptive Korean gloss to use.
    if language == "ko" and gloss and kind and gloss == kind and len(gloss) <= 10:
        richer = [g for g in defs if _HANGUL.search(g) and g != kind and len(g) >= 12]
        if not richer:
            return None

    from packages.base_brain.korean_orthography import josa

    if language == "ko":
        if gloss and _HANGUL.search(gloss):

            text = f"{josa(subject, 'topic')} {josa(gloss, 'copula')}."
        elif gloss:  # english gloss for a korean asker — frame it honestly as dictionary data
            text = f"{josa(subject, 'topic')} 사전상 '{gloss}'라는 뜻이에요."
        else:
            text = f"{josa(subject, 'topic')} {kind}의 하나예요."
        # append the category only when it adds information the gloss didn't already state
        if kind and gloss and kind not in gloss:
            text += f" {kind}에 속해요."
    else:
        if gloss:
            text = f"{subject} — {gloss.rstrip('.')}."
        else:
            text = f"{subject} is a kind of {kind}."
        if kind and gloss and kind.lower() not in gloss.lower():
            text += f" ({_article(kind)} {kind})"

    grounding = [[s, p, o] for s, p, o in rows[:6]]
    return {
        "answer": text,
        "grounding": grounding,
        "certificate": {
            "derivation_kind": "lexicon_cartridge",
            "source": "kaikki_wiktionary",
            "license": "CC BY-SA",
            "store": str(_STORE_PATH),
            "facts_used": len(grounding),
        },
        "guarantees": {"external_llm": False, "fabricated_facts": False, "verbatim_dictionary": True},
    }
