# -*- coding: utf-8 -*-
"""Conversational surface transforms — CONTRACTIONS as a FORM-only, function-word pass over an
already-assembled, faithful surface, plus their EXACT inverse for the faithfulness scorer.

A contraction rewrites a CLOSED, function-word sequence — a subject/pronoun + auxiliary, or an
auxiliary + 'not' — into its clitic form: ``it is`` -> ``it's``, ``they are`` -> ``they're``,
``does not`` -> ``doesn't``. It NEVER touches a content word, so a contracted surface preserves the
EXACT fact set of its expansion. This is the same honesty contract the rest of the fluency package
holds: register changes HOW something is said, never WHAT.

``expand_contractions`` is the exact inverse the faithfulness scorer applies BEFORE tokenizing, so a
clitic is measured as its function-word expansion (a contraction IS its expansion) rather than being
mis-tokenized into a spurious content fragment (``it's`` -> ``it`` + ``s``). Because every expansion is
a closed-class function word, this can never let an invented CONTENT word past the faithfulness gate —
a planted fabrication like "amazing" has no clitic and is still flagged.

Deliberately NOT contracted: ``has``/``have`` to ``'s``/``'ve`` — ``it has a mane`` -> ``it's a mane``
would change the meaning (``'s`` reads as ``is``). Only the copula/auxiliary ``is``/``are``/``am`` and
the negations are contracted, which keeps the transform meaning-preserving by construction.
"""
from __future__ import annotations

import re

# a subject we refuse to contract 'is' after: one ending in a sibilant, where "'s" is awkward or reads
# oddly (Paris -> "Paris's", box -> "box's", buzz -> "buzz's"). Keep the full 'is' there.
_NO_S_AFTER = re.compile(r"[sxzSXZ]$")

# words that must never take the 's contraction even though they don't end in a sibilant: 'which is
# why' is an approved discourse connective — contracting it to "which's why" would corrupt it.
_IS_CONTRACT_EXCLUDE = frozenset({"which"})

# auxiliary + 'not' -> clitic. Affirmative bones rarely reach these, but the realizer stays correct if
# a negated bone ever appears.
_NEG = {
    "is not": "isn't", "are not": "aren't", "was not": "wasn't", "were not": "weren't",
    "has not": "hasn't", "have not": "haven't", "had not": "hadn't",
    "does not": "doesn't", "do not": "don't", "did not": "didn't",
    "would not": "wouldn't", "should not": "shouldn't", "could not": "couldn't",
    "must not": "mustn't", "cannot": "can't", "can not": "can't", "will not": "won't",
}
_NEG_PAT = re.compile(
    r"\b(?:cannot|can not|will not|would not|should not|could not|must not|is not|are not|"
    r"was not|were not|has not|have not|had not|does not|do not|did not)\b",
    re.IGNORECASE,
)


def _apply_case(template: str, sample: str) -> str:
    """Give `template` the leading-capital of `sample` (so 'Is not' -> "Isn't" at sentence start)."""
    if sample[:1].isupper():
        return template[:1].upper() + template[1:]
    return template


def contract(text: str) -> str:
    """Apply the closed, function-word-only conversational contractions to an assembled surface.

    Only copular/auxiliary ``is``/``are``/``am`` and the ``aux + not`` negations are contracted; the
    subject and every content word are left byte-identical. The transform is meaning-preserving by
    construction (it rewrites function words only)."""
    if not text:
        return text
    s = text

    # <pronoun> are -> <pronoun>'re  (only the pronominal plural subjects; noun+'re is nonstandard)
    s = re.sub(r"\b(they|we|you|They|We|You)\s+are\b", lambda m: m.group(1) + "'re", s)

    # I am -> I'm
    s = re.sub(r"\b(I|i)\s+am\b", lambda m: m.group(1) + "'m", s)

    # <subject> is -> <subject>'s  (pronoun always; a noun unless it ends in a sibilant / is excluded)
    def _is(m: "re.Match[str]") -> str:
        w = m.group(1)
        if w.lower() in _IS_CONTRACT_EXCLUDE or _NO_S_AFTER.search(w):
            return m.group(0)
        return w + "'s"

    s = re.sub(r"\b([A-Za-z][A-Za-z-]*)\s+is\b", _is, s)

    # negations
    def _neg(m: "re.Match[str]") -> str:
        phrase = m.group(0)
        repl = _NEG.get(phrase.lower())
        return _apply_case(repl, phrase) if repl else phrase

    s = _NEG_PAT.sub(_neg, s)
    return s


def expand_contractions(text: str) -> str:
    """The exact inverse of :func:`contract` for the faithfulness scorer: map every clitic back to its
    closed-class function-word expansion so it is measured as a function word, never a content token.

    Order matters: the irregular ``can't``/``won't``/``shan't`` are handled before the generic ``n't``
    rule, and the generic ``'s`` -> `` is`` runs last. Every replacement target is a function word, so
    this can only make the faithfulness scorer treat a clitic as its (function-word) expansion — it
    never turns a fabricated CONTENT word into a grounded one."""
    if not text or "'" not in text:
        return text
    s = text
    s = re.sub(r"\bcan't\b", "can not", s, flags=re.IGNORECASE)
    s = re.sub(r"\bwon't\b", "will not", s, flags=re.IGNORECASE)
    s = re.sub(r"\bshan't\b", "shall not", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(\w+)n't\b", r"\1 not", s)            # isn't->is not, doesn't->does not, ...
    s = re.sub(r"\b(\w+)'re\b", r"\1 are", s)
    s = re.sub(r"\b(\w+)'ve\b", r"\1 have", s)
    s = re.sub(r"\b(\w+)'ll\b", r"\1 will", s)
    s = re.sub(r"\b(\w+)'m\b", r"\1 am", s)
    s = re.sub(r"\b(\w+)'d\b", r"\1 would", s)
    s = re.sub(r"\b(\w+)'s\b", r"\1 is", s)              # our generated 's is always the copula 'is'
    return s


# clitic detector for the OUTPUT contraction-rate metric (a token carrying a contraction apostrophe).
_CLITIC = re.compile(r"\b\w+(?:'s|'re|'m|'ve|'ll|'d|n't)\b", re.IGNORECASE)
# an UN-contracted, contractible site the conversational pass could still collapse (pronoun/subject +
# copula, pronominal subject + are/am, or an aux+not) — used as the denominator of contraction_rate.
_CONTRACTIBLE_SITE = re.compile(
    r"\b[A-Za-z][A-Za-z-]*\s+is\b|\b(?:they|we|you)\s+are\b|\bI\s+am\b|"
    r"\b(?:is|are|was|were|has|have|had|does|do|did|would|should|could|must|can|will)\s+not\b|"
    r"\bcannot\b",
    re.IGNORECASE,
)


def count_clitics(text: str) -> int:
    return len(_CLITIC.findall(text or ""))


def count_contractible_sites(text: str) -> int:
    """Un-contracted sites still collapsible by :func:`contract` (a 'noun/pronoun is' that we would
    actually contract — excluding sibilant-final subjects we intentionally leave alone)."""
    n = 0
    for m in _CONTRACTIBLE_SITE.finditer(text or ""):
        frag = m.group(0)
        mis = re.match(r"([A-Za-z][A-Za-z-]*)\s+is$", frag, re.IGNORECASE)
        if mis and (mis.group(1).lower() in _IS_CONTRACT_EXCLUDE or _NO_S_AFTER.search(mis.group(1))):
            continue                                    # a site contract() would decline -> not a site
        n += 1
    return n
