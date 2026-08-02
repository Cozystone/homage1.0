# -*- coding: utf-8 -*-
"""Targeted relational-fact extractor — PURE, side-effect-free (no disk, no network).

The GAP this fills (measured 2026-07-22): the existing web learners only mine COPULAR
DEFINITIONS (``corpus_adapters.extract_definition_triple`` -> ``is_a`` / ``defined_as``).
They cannot mine a RELATIONAL edge like ``(France, capital, Paris)`` from prose, so the
"capital of France?" abstention could never be closed by autonomous acquisition — only by a
pre-seeded Wikidata pull (``knowledge_harvest``). This module is the missing organ: given a
KNOWN missing fact ``(entity, relation)`` — which the abstaining question already names — it
finds the OBJECT in a document with high-precision SURFACE patterns.

Why targeted (not open IE) is safe: we are never doing open extraction. The abstention already
tells us WHAT is missing (entity + relation); we only need the object. So every pattern is
anchored on the KNOWN entity AND the KNOWN relation surface word — a French capital sentence
cannot misfire as a German-currency fact. Residual over-capture (a stray noun) is caught by the
downstream >= 2-DISTINCT-DOMAIN consensus gate (``consensus.py``): an extraction error rarely
agrees with an independent stranger on the SAME wrong object.

The relation lexicon reused here (``REL_SYNONYMS`` from base_brain.relational_lookup) is the LAD
surface layer — relation NAMES and their surface synonyms, not world facts (the same class the
graph already uses). The verb-conjugation table is surface morphology (LAD), not knowledge.
"""
from __future__ import annotations

import re
from typing import Iterable

# reuse the relation-label lexicon (LAD surface layer) the graph + relational lane already use
from packages.base_brain.relational_lookup import REL_SYNONYMS

# ── verb relations: surface conjugation only (LAD morphology, not world knowledge) ───────────────
# rel_norm (from relational_lookup._INVERTED_VERBS) -> (active form, passive participle).
_VERB_FORMS: dict[str, tuple[str, str]] = {
    "wrote": ("wrote", "written"),
    "written by": ("wrote", "written"),
    "author": ("wrote", "written"),
    "painted": ("painted", "painted"),
    "composed": ("composed", "composed"),
    "directed": ("directed", "directed"),
    "founded": ("founded", "founded"),
    "invented": ("invented", "invented"),
    "designed": ("designed", "designed"),
    "built": ("built", "built"),
    "created": ("created", "created"),
    "discovered": ("discovered", "discovered"),
}

# object noun-phrase run: 1..4 tokens of letters/digits/.'- (proper nouns, "New York City",
# "William Shakespeare", "Buenos Aires", "the yen"); an article is consumed, not captured.
_NP = r"[A-Za-z0-9][A-Za-z0-9.'\-]*(?:\s+[A-Za-z0-9.'\-]+){0,3}"
_TITLE_NP = r"[A-Z][A-Za-z0-9.'\-]*(?:\s+[A-Z][A-Za-z0-9.'\-]*){0,3}"
_ART = r"(?:the\s+|a\s+|an\s+)?"

# words that are never a valid object head (function / discourse words); a captured object whose
# WHOLE value is one of these is dropped. Surface layer.
_STOP_OBJ = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "these", "those", "there", "here", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "by", "as", "from", "which", "who", "what", "where", "when", "also", "one", "both",
    "known", "called", "located", "situated", "considered", "same", "such", "not", "no", "yes",
    "home", "seat", "site", "part", "member", "capital", "city", "country", "nation", "state",
}
# clause / preposition boundaries that end an object noun phrase (so we don't swallow a clause)
_OBJ_TAIL = re.compile(
    r"\s*(?:,|\.|;|:|\(|\)|\band\b|\bwhich\b|\bwhere\b|\bwith\b|\bthat\b|\bis\b|\bwas\b|\bhas\b|"
    r"\bhad\b|\bon\b|\bin\b|\bfor\b|\bafter\b|\bsince\b|\buntil\b|\bfrom\b|\bto\b|\bas\b|\bbut\b)",
    re.IGNORECASE)


def _clean_obj(raw: str, entity: str) -> str | None:
    """Trim a captured object to a clean noun phrase; None if it is empty / a stopword / the
    entity itself. Pure surface cleanup — never rewrites the token, only trims boundaries."""
    o = re.sub(r"\s+", " ", str(raw or "")).strip()
    o = re.sub(r"^(?:the|a|an)\s+", "", o, flags=re.IGNORECASE).strip()
    # cut at the first clause/preposition boundary AFTER the first token (keep multiword names)
    m = _OBJ_TAIL.search(o, pos=1)
    if m:
        o = o[:m.start()].strip()
    o = o.strip(" ,.;:'\"-)(").strip()
    # LIVE-page cleanup (surface only): real menu/heading/coordinate text yields dirty captures the
    # clean-prose sealed corpus never contains. Fold them so the SAME value corroborates across
    # domains instead of fragmenting into non-consensus variants:
    #   * strip a leading stray single letter ("E Astana" -> "Astana"; the article a/an/the was
    #     already removed above, so a lone leading letter here is coordinate/fragment noise);
    #   * collapse an immediate duplicate-token run ("Astana Astana" -> "Astana").
    toks = o.split()
    if len(toks) >= 2 and len(toks[0]) == 1 and toks[0].isalpha():
        toks = toks[1:]
    dedup: list[str] = []
    for tk in toks:
        if not dedup or dedup[-1].lower() != tk.lower():
            dedup.append(tk)
    o = " ".join(dedup)
    # a QUANTITY object is '<number> <scale?>' — drop a trailing descriptive noun so surface
    # variants corroborate ('68 million people' == '68 million'). Surface rule (a digit-led object
    # is a magnitude), leaves Title-case names untouched.
    if o[:1].isdigit():
        mq = re.match(r"\d[\d.,]*(?:\s+(?:hundred|thousand|million|billion|trillion))?", o, re.I)
        if mq and mq.group(0).strip():
            o = mq.group(0).strip()
    if not o or len(o) < 2 or len(o) > 48:
        return None
    if o.lower() in _STOP_OBJ:
        return None
    # a lone lowercase -ed/-ing token is a captured VERB ('the capital was moved to ...', 'being
    # founded'), never a proper value — drop it (proper-noun values are Title-case; 'yen' etc. are
    # kept). Verb relations use the separate Title-case _VERB_FORMS path, so this cannot hit them.
    if " " not in o and o.islower() and (o.endswith("ed") or o.endswith("ing")):
        return None
    if o.lower() == entity.strip().lower() or entity.strip().lower() in o.lower().split():
        return None
    return o


def _rel_surface(rel_norm: str) -> list[str]:
    """Surface relation phrases to search for: the rel_norm itself plus any prose synonyms
    (underscored graph-id labels like 'capital_of' are skipped — those are predicate ids, not
    prose). LAD surface layer. Longest first so the specific phrase matches before a substring."""
    forms = {rel_norm}
    for label in REL_SYNONYMS.get(rel_norm, frozenset()):
        if "_" not in label:                     # skip graph-id style labels
            forms.add(label)
    out = [f for f in forms if re.fullmatch(r"[a-zA-Z ]+", f)]
    return sorted(out, key=len, reverse=True)


def _ci(s: str) -> str:
    """Case-insensitive inline group for an anchor literal (so the GLOBAL flag stays off and the
    Title-case object patterns keep their real case-sensitivity)."""
    return f"(?i:{s})"


def extract_relation_facts(text: str, entity: str, rel_norm: str,
                           kind: str = "of") -> list[str]:
    """From ONE document/segment, extract candidate OBJECT values for the KNOWN
    ``(entity, rel_norm)`` fact, using high-precision surface patterns anchored on both the
    entity and the relation. Returns a de-duplicated list of verbatim object strings (possibly
    empty). Pure. The caller tallies these across domains and only a >= 2-domain object is kept.
    """
    if not text or not entity or not rel_norm:
        return []
    t = re.sub(r"\s+", " ", str(text))
    ent = _ci(re.escape(entity.strip()))
    art = _ci("the |a |an ") + "?"
    is_w = _ci("is|was|are|were")
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: str | None) -> None:
        o = _clean_obj(raw, entity) if raw else None
        if o and o.lower() not in seen:
            seen.add(o.lower())
            out.append(o)

    if kind == "verb" and rel_norm in _VERB_FORMS:
        active, passive = (_ci(f) for f in _VERB_FORMS[rel_norm])
        # "Hamlet was written by William Shakespeare"  (object = a real Title-case name)
        for m in re.finditer(rf"{ent}\s+(?:{is_w}|{_ci('has been')})\s+{passive}\s+{_ci('by')}\s+"
                             rf"(?P<o>{_TITLE_NP})", t):
            _add(m.group("o"))
        # "William Shakespeare wrote Hamlet"
        for m in re.finditer(rf"(?P<o>{_TITLE_NP})\s+{active}\s+{art}{ent}\b", t):
            _add(m.group("o"))
        return out

    # optional apposition head between the relation noun and "of": "capital [city] of",
    # "capital [region] of", "capital [metropolitan area] of" — the near-universal encyclopedic
    # phrasing ("Astana is the capital city of Kazakhstan"). LAD surface layer (generic geo/category
    # head nouns, not world facts); the group is OPTIONAL so plain "capital of" prose is unchanged —
    # it only ADDS matches, never removes one, so the clean-prose sealed gate is unaffected.
    appos = _ci(r"(?:\s+(?:city|cities|region|province|area|metropolis|metropolitan\s+area))?")
    # attribute relations ("capital", "currency", "official language", ...)
    for rel in _rel_surface(rel_norm):
        rel_re = _ci(re.escape(rel))
        of = _ci("of")
        rel_of = rf"{rel_re}{appos}\s+{of}"
        # A) "the <REL> of <ENTITY> is <OBJ>"  /  "... of <ENTITY>: <OBJ>"
        for m in re.finditer(
                rf"{rel_of}\s+{art}{ent}\s*(?:{is_w}|:|=|—|-)\s+{art}(?P<o>{_NP})", t):
            _add(m.group("o"))
        # B) "<ENTITY>'s <REL> is <OBJ>"  /  "<ENTITY>'s <REL>, <OBJ>,"
        for m in re.finditer(rf"{ent}'s\s+{rel_re}{appos}\s*(?:{is_w}|:|,)\s+{art}(?P<o>{_NP})", t):
            _add(m.group("o"))
        # C) "<OBJ> is the <REL> of <ENTITY>"  /  "<OBJ>, the <REL> of <ENTITY>"
        for m in re.finditer(rf"(?P<o>{_TITLE_NP})\s*(?:{is_w}|,)\s+{art}{rel_of}\s+{art}{ent}\b", t):
            _add(m.group("o"))
        # D) forward appositive "the <REL> of <ENTITY>, <OBJ>" ("As the capital of France, Paris ...")
        for m in re.finditer(rf"{rel_of}\s+{art}{ent}\s*,\s+(?P<o>{_TITLE_NP})\b", t):
            _add(m.group("o"))

    # PROPERTY RELATIONS take a different surface entirely, and the patterns above cannot see them.
    # Measured 2026-07-31 on textbook sentences: "Paris is the capital of France" yields Paris, while
    #   "A trowel is a small hand tool used for digging"        -> []
    #   "Modern bollards are made of steel or concrete"          -> []
    #   "a bird of prey that can hover in the air while hunting" -> []
    # all return nothing. The reason is structural rather than a missing pattern: what a thing is FOR
    # is written as a participial or relative clause hanging off the definition, never as "the used-for
    # of a trowel is digging", so an <OBJ>-<REL>-<ENTITY> template has nothing to anchor on. That gap
    # is exactly why the store holds 39,673 used_for against 44 million is_a.
    #
    # The judgement is NOT re-implemented here. packages.graph_scale.property_extraction already owns
    # it for the dictionary and Wikipedia-lead harvesters, and a third copy would drift from both.
    if not out:
        out.extend(_property_objects(t, entity, rel_norm))
    return out


# rel_norm as the shape parser produces it -> the predicate property_extraction emits.
_PROPERTY_RELS = {"used for": "used_for", "capable of": "capable_of", "made of": "made_of",
                  "used_for": "used_for", "capable_of": "capable_of", "made_of": "made_of"}


def _property_objects(text: str, entity: str, rel_norm: str) -> list[str]:
    """Objects for a property relation, delegated to the shared extractor. Empty for anything else.

    Sentence-scoped on purpose: the shared extractor reads ONE definitional sentence, and running it
    over a whole fetched page would let a clause about some other noun attach itself to this entity.
    A sentence is kept only if it mentions the entity."""
    want = _PROPERTY_RELS.get(str(rel_norm).strip().lower())
    if not want:
        return []
    try:
        from packages.graph_scale.property_extraction import extract as _prop_extract
    except Exception:
        return []
    ent = str(entity).strip().lower()
    found: list[str] = []
    seen: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if ent not in sentence.lower():
            continue
        for pred, obj in _prop_extract(ent, sentence):
            if pred == want and obj not in seen:
                seen.add(obj)
                found.append(obj)
    return found


def extract_from_documents(docs: Iterable[tuple[str, str]], entity: str, rel_norm: str,
                           kind: str = "of") -> list[tuple[str, str]]:
    """Extract (object, source_url) pairs across many (url, text) documents. A single document may
    yield several candidate objects; each is tagged with its source url so the consensus tally can
    count DISTINCT DOMAINS. Pure."""
    pairs: list[tuple[str, str]] = []
    for url, text in docs:
        for obj in extract_relation_facts(text, entity, rel_norm, kind):
            pairs.append((obj, url))
    return pairs
