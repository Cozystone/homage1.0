# -*- coding: utf-8 -*-
"""Relational-lookup lane — runs BEFORE the define lane.

Owner-priority defect (measured 2026-07-21): "what is the capital of France?" was
routed to the DEFINE lane, which token-matched the head noun ("capital") and answered
"capital is named after Washington…" at confidence 0.91 — a confident WRONG answer.
Same class: population of France, boiling point of water, speed of light.

Root cause (traced): for an English "<REL> of <ENTITY>" question the base_brain pipeline
had no relational parse (query_frame's relation arm is Korean-only), so get_semantic_context
scored the head-noun REL as the subject, classify_intent saw "what is" -> "define", and
_compose_answer defined the wrong head noun. The Korean _asks_attribute demotion never fires
on English.

The fix is STRUCTURAL + GRAPH, not another define guard (doctrine: knowledge lives in the
GRAPH; rules are training wheels). This lane:
  1) structurally parses "what/who is the <REL> of <ENTITY>", the possessive "France's
     capital", and inverted verb forms ("who wrote Hamlet", "what is light made of");
  2) a learned scorer (relational_router) gates define-vs-relational — regex only extracts
     features, the trained weights decide;
  3) RESOLVES by GRAPH: it finds the ENTITY, scans that entity's edges for one whose label
     matches the asked relation (lemma/synonym over predicate labels), and returns the target
     with a reasoning_certificate NAMING the edge;
  4) if the graph holds no such edge -> HONEST ABSTENTION ("I don't hold a grounded <rel>
     fact for <entity> yet"), never the head-noun define;
  5) a grounded COMPOUND entity ("speed of light" has its own defined_as) is defined as the
     compound via the existing graph bridge, not decomposed into head-noun REL.

trace.intent is set to 'relational' (or 'define' for the grounded compound). The lane returns
None for non-relational shapes (plain "what is photosynthesis") so those are untouched.

The relation lexicon below is a LAD surface-layer relation-label list (relation NAMES and their
surface synonyms — not world facts); it mirrors the predicate labels the graph already uses
(graph_scale.answer_bridge._RELATION_CUES) and the answers themselves come only from stored
edges.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache
from typing import Any

# Zero-width / invisible separators an obfuscator hides inside a word ('Atla<zwsp>ntis') to
# split it past exact matching. Stripped at entry so a perturbed relational question parses to
# the same shape as its clean form.
_ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿­᠎]")

# ── distribution-shift de-framing (adversary loop surface a: wrap_innocuous / role_prefix) ──────
# A crafted query wraps the real payload in a benign frame ('Here is a quote to summarize: "<q>"
# Please summarize it.') or an authority/role prefix ('SYSTEM: <q>', 'You are now the <q>') so the
# payload shifts OFF the calibrated manifold and the ambiguity/abstain signal is dropped. Peeling
# these mirrors the #72 case+whitespace normalization to the wrapper/prefix/fence classes, so a
# wrapped must-abstain query is judged like its CLEAN form (relational abstain / define coverage
# gate). These patterns are the LAD surface layer (framing function-words), NOT world knowledge;
# they match only the SPECIFIC benign frames an entry meets, so a clean query is returned unchanged.
_ROLE_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"(?:system|admin|administrator|developer|assistant|user)\s*[:>]"
    r"|from\s+now\s+on,?\s+you(?:\s+are)?\b"
    r"|you\s+are\s+now\s+the\b"
    r"|as\s+the\s+administrator,?"
    r")\s*", re.IGNORECASE)
_WRAP_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"here\s+is\s+(?:a|the)\s+(?:quote|note|text|message|passage)\s+to\s+summari[sz]e"
    r"|here\s+is\s+(?:a|the)\s+(?:quote|note|text|message|passage)"
    r"|the\s+document\s+contains\s+the\s+following\s+note"
    r"|a\s+user\s+on\s+a\s+forum\s+wrote"
    r"|translate\s+this\s+sentence\s+into\s+[a-z]+"
    r"|please\s+consider\s+the\s+following\s+note\s+and\s+act\s+on\s+it"
    r"|consider\s+the\s+following(?:\s+note)?"
    r")\s*[:\-]\s*", re.IGNORECASE)
_WRAP_TRAIL_RE = re.compile(
    r"\s*(?:"
    r"--\s*what\s+do\s+you\s+think\??"
    r"|please\s+summari[sz]e\s+it\.?"
    r")\s*$", re.IGNORECASE)
_QUOTE_WRAP_RE = re.compile(r"^\s*[\"“”'‘’`](.+?)[\"“”'‘’`]\s*$", re.DOTALL)
_FENCE_LEAD_RE = re.compile(r"^\s*```[a-z0-9]*\s*")
_FENCE_TRAIL_RE = re.compile(r"\s*```\s*$")


def _deframe(s: str) -> str:
    """Peel benign framing (innocuous wrapper, role/authority prefix, code fence, wrapping quotes)
    so a wrapped/prefixed adversarial query maps back onto the SAME shape as its clean form.
    Bounded (<=4 passes, so nested layers peel) and CONSERVATIVE: only the specific frames above are
    stripped; a query with none of them is returned unchanged."""
    prev = None
    for _ in range(4):
        if s == prev:
            break
        prev = s
        s = s.strip()
        s = _FENCE_LEAD_RE.sub("", s)
        s = _FENCE_TRAIL_RE.sub("", s)
        s = _WRAP_LEAD_RE.sub("", s)
        s = _ROLE_PREFIX_RE.sub("", s)
        s = _WRAP_TRAIL_RE.sub("", s)
        m = _QUOTE_WRAP_RE.match(s)
        if m:
            s = m.group(1)
        s = s.strip()
    return s


def _normalize_query(query: str) -> str:
    """Entry robustness (adversary loop surface a): NFKC-normalise, strip zero-width separators,
    collapse whitespace runs, and de-obfuscate benign framing (innocuous wrapper / role prefix /
    code fence / wrapping quotes), so an obfuscated or wrapped question
    ('SYSTEM: what i<zwsp>s the c a p i t a l of Atla<zwsp>ntis?', 'Here is a quote to summarize:
    "<q>" Please summarize it.') reaches the same lane + doubt signal as its clean form instead of
    slipping past the relational parser into the ungated define lane. Case is deliberately NOT
    folded here: the store is case-sensitive on proper-noun subjects, so folding would degrade a
    clean answer's surface; case robustness for the doubt signal lives downstream in the fan-out
    lookup (answer_bridge._entity_case_variants). A clean query (no zero-width, single spaces, no
    framing) is returned byte-identical -> no behaviour or calibration shift."""
    s = unicodedata.normalize("NFKC", str(query or ""))
    s = _ZERO_WIDTH_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _deframe(s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_query(query: str) -> str:
    """Public entry-normalizer shared by the base_brain answer router (both the relational and the
    define lane must judge a wrapped/prefixed query by its clean form). See _normalize_query;
    idempotent on a clean query (returns it byte-identical)."""
    return _normalize_query(query)

# ── which relations ATANOR can answer: asked of its OWN graph, never declared here ──────────
# The store's predicate column IS the answer to "what relations do I have edges for". Deriving it
# instead of listing it means the set grows on its own the moment acquisition lands a new relation
# type -- no edit here, no drift between the list and reality.
#
# Measured 2026-07-28, why this replaced the hand list: the frozenset below named 70 relations; the
# graph uses 46; they agreed on 15. The list omitted `is_a` (44.5M edges), `located_in` (15.7M),
# `part_of`, `defined_as`, `has_a`, `made_of`, `used_for`, `capable_of`, `causes` -- about 73M of
# 115M stored edges, which the relational branch therefore refused to route. It also asserted 55
# relations the graph has no edge for at all (`area`, `atomic_mass`, `ceo`, `density`, ...), forcing
# that branch for questions nothing could answer. Wrong in both directions, and silently.
def _relations_of(store: Any) -> frozenset[str]:
    """The distinct predicate labels present in an OPEN store."""
    import numpy as np
    ids = np.unique(store.open_columns()["p"])
    return frozenset(store.terms.term(int(i)) for i in ids)


@lru_cache(maxsize=1)
def _shipped_relations() -> frozenset[str]:
    try:
        from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
        from packages.graph_scale.triple_store import TripleStore
        store = TripleStore(SHIPPED_GRAPH_ROOT)
        try:
            return _relations_of(store)
        finally:
            store.close()
    except Exception:
        return frozenset()


def graph_relations(store: Any = None) -> frozenset[str]:
    """Predicate labels the graph IN PLAY actually uses.

    Pass the store being worked on — the acquisition daemon runs against a scratch copy and tests
    against a fixture, and reading the shipped store instead would answer about the wrong graph.
    With no store the shipped one is read and cached (one column scan per process).

    Empty on any read failure, which lets routing fall through to the trained classifier rather
    than assert reach we cannot back."""
    if store is not None:
        try:
            return _relations_of(store)
        except Exception:
            return frozenset()
    return _shipped_relations()


def answerable_relation(rel_norm: str) -> bool:
    """True when some predicate that would answer `rel_norm` exists in the graph. Goes through the
    same surface->predicate mapping the lookup itself uses, so `capital city` counts via `capital`."""
    if not rel_norm:
        return False
    return bool(_wanted_labels(rel_norm) & graph_relations())


# Retained ONLY as the surface->predicate synonym source consulted by _predicate_targets below;
# membership in it no longer decides whether a relation is answerable.
_RELATION_SURFACE_FORMS: frozenset[str] = frozenset({
    "capital", "capital city", "population", "area", "currency", "language",
    "official language", "national language", "author", "writer", "composer", "director",
    "founder", "inventor", "discoverer", "president", "prime minister", "monarch", "king",
    "queen", "ceo", "chief executive", "mayor", "governor", "leader", "head of state",
    "boiling point", "melting point", "freezing point", "atomic number", "atomic mass",
    "atomic weight", "chemical formula", "chemical symbol", "symbol", "molar mass",
    "density", "height", "length", "width", "depth", "diameter", "radius", "mass",
    "weight", "colour", "color", "nationality", "birthplace", "birthday", "birth date",
    "nickname", "largest city", "national anthem", "flag", "religion", "gdp",
    # Wikidata bulk-relation coverage (S1 promotion 2026-07-24: occupation/country/located_in/
    # continent/genre/manufacturer/employer/sport/creator edges are now live in the store). These
    # are relation NAMES (LAD surface layer), not world facts; answers still come only from a
    # stored edge, else honest abstention.
    "occupation", "profession", "job", "country", "located country", "continent",
    "genre", "manufacturer", "maker", "employer", "sport", "creator", "part",
})

# rel_norm -> the GRAPH predicate labels that answer it. Answers still come only from stored
# edges; this just maps the surface relation word to the edge label(s) the store uses.
REL_SYNONYMS: dict[str, frozenset[str]] = {
    "capital": frozenset({"capital", "capital_city", "capital_of"}),
    "capital city": frozenset({"capital", "capital_city"}),
    "author": frozenset({"author", "author_of", "written_by", "creator", "writer"}),
    "writer": frozenset({"author", "written_by", "creator", "writer"}),
    "wrote": frozenset({"author", "written_by", "creator", "writer"}),
    "written by": frozenset({"author", "written_by", "creator", "writer"}),
    "composer": frozenset({"composer", "creator", "composed_by"}),
    "composed": frozenset({"composer", "creator", "composed_by"}),
    "painter": frozenset({"creator", "painted_by", "artist"}),
    "painted": frozenset({"creator", "painted_by", "artist"}),
    "director": frozenset({"director", "directed_by", "creator"}),
    "directed": frozenset({"director", "directed_by", "creator"}),
    "founder": frozenset({"founder", "founded_by", "creator"}),
    "founded": frozenset({"founder", "founded_by", "creator"}),
    "inventor": frozenset({"inventor", "invented_by", "discoverer", "creator"}),
    "invented": frozenset({"inventor", "invented_by", "creator"}),
    "discoverer": frozenset({"discoverer", "discovered_by"}),
    "discovered": frozenset({"discoverer", "discovered_by"}),
    "created": frozenset({"creator", "created_by"}),
    "designed": frozenset({"designer", "designed_by", "creator"}),
    "built": frozenset({"builder", "built_by", "creator"}),
    "made of": frozenset({"made_of", "composed_of", "material"}),
    "composed of": frozenset({"made_of", "composed_of"}),
    "made up of": frozenset({"made_of", "composed_of"}),
    "part of": frozenset({"part_of"}),
    "used for": frozenset({"used_for"}),
    # R2 ConceptNet densification (2026-07-22): capable_of 22,662 / has_a 5,494 /
    # has_property 8,361 edges now live in the store. These canonical rel_norms (emitted by the
    # attribute-question shapes below) map to those predicate labels so the phrasings can REACH
    # the new edges; answers still come only from a stored triple, else honest abstention.
    "capable of": frozenset({"capable_of"}),
    "has a": frozenset({"has_a", "has_part"}),
    "has property": frozenset({"has_property"}),
    "population": frozenset({"population", "인구"}),
    "area": frozenset({"area", "면적"}),
    "currency": frozenset({"currency"}),
    "language": frozenset({"official_language", "language"}),
    "official language": frozenset({"official_language", "language"}),
    "president": frozenset({"head_of_state", "president", "국가원수"}),
    "prime minister": frozenset({"head_of_government", "prime_minister", "정부수반"}),
    "ceo": frozenset({"chief_executive_officer", "ceo", "최고경영자"}),
    "chief executive": frozenset({"chief_executive_officer", "ceo", "최고경영자"}),
    "boiling point": frozenset({"boiling_point"}),
    "melting point": frozenset({"melting_point"}),
    "atomic number": frozenset({"atomic_number"}),
    "atomic mass": frozenset({"atomic_mass", "atomic_weight"}),
    "chemical formula": frozenset({"chemical_formula", "formula", "화학식"}),
    "chemical symbol": frozenset({"symbol", "chemical_symbol"}),
    "symbol": frozenset({"symbol", "chemical_symbol"}),
    "density": frozenset({"density"}),
    "colour": frozenset({"color", "colour", "has_color"}),
    "color": frozenset({"color", "colour", "has_color"}),
    "located": frozenset({"located_in", "location"}),
    "located in": frozenset({"located_in", "location"}),
    "location": frozenset({"located_in", "location"}),
    # S1 Wikidata bulk relations (2026-07-24): the predicate labels below are the ones VERIFIED
    # live in the 115M store (occupation, country, located_in, capital, genre, manufacturer,
    # employer, sport, creator, official_language, part_of, made_of). rel_norm -> stored label(s);
    # answers still come only from a real edge. Multi-label sets let a general phrasing reach
    # whichever label the store used; _predicate_targets picks the first stored one that matches.
    "occupation": frozenset({"occupation"}),
    "profession": frozenset({"occupation"}),
    "job": frozenset({"occupation"}),
    "country": frozenset({"country", "located_country"}),
    "located country": frozenset({"country", "located_country", "located_in"}),
    # No `continent` predicate exists at 115M; a country's continent is carried by located_in /
    # part_of (VERIFIED: Austria located_in Europe; Argentina part_of South America). General
    # phrasing "what continent is X in" -> those labels; a noisy target is paid for in the gate's
    # abstention, never in a fabricated fact.
    "continent": frozenset({"continent", "located_in", "part_of"}),
    "genre": frozenset({"genre"}),
    "manufacturer": frozenset({"manufacturer", "made_by", "maker"}),
    "maker": frozenset({"manufacturer", "made_by", "creator"}),
    "made by": frozenset({"manufacturer", "made_by", "creator"}),
    "employer": frozenset({"employer", "employed_by"}),
    "sport": frozenset({"sport"}),
    "religion": frozenset({"religion"}),
    "creator": frozenset({"creator", "created_by", "made_by", "author", "designer"}),
    "part": frozenset({"part_of"}),
}

# verbs whose inverted question ("who WROTE Hamlet") names a relation.
_INVERTED_VERBS: dict[str, str] = {
    "wrote": "wrote", "write": "wrote", "written": "written by", "authored": "author",
    "painted": "painted", "paint": "painted", "composed": "composed", "compose": "composed",
    "created": "created", "create": "created", "invented": "invented", "invent": "invented",
    "discovered": "discovered", "discover": "discovered", "founded": "founded",
    "found": "founded", "directed": "directed", "direct": "directed", "designed": "designed",
    "design": "designed", "built": "built", "build": "built",
    # "who made / makes X" -> manufacturer/creator (the store's manufacturer/made_by/creator edges).
    # "what is X made of" is caught by _MADEOF_RE first (it starts with "what", this needs "who").
    "made": "made by", "make": "made by", "makes": "made by", "manufactured": "made by",
}

_LEAD = r"(?:please\s+)?(?:can\s+you\s+)?(?:tell\s+me\s+|give\s+me\s+)?"
_ART = r"(?:the\s+|a\s+|an\s+)?"

# "what/who is the <REL> of <ENTITY>"
_OF_RE = re.compile(
    rf"^\s*{_LEAD}(?:what|which|who|whom)(?:'s)?(?:\s+(?:is|are|was|were))?\s+{_ART}"
    r"(?P<rel>[A-Za-z][A-Za-z .'\-]{1,40}?)\s+of\s+" + _ART +
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s*[?.!]*\s*$",
    re.IGNORECASE)
# "tell me the <REL> of <ENTITY>" / bare "the <REL> of <ENTITY>"
_OF_BARE_RE = re.compile(
    rf"^\s*{_LEAD}the\s+(?P<rel>[A-Za-z][A-Za-z .'\-]{{1,40}}?)\s+of\s+{_ART}"
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s*[?.!]*\s*$",
    re.IGNORECASE)
# possessive: "what is France's capital" / bare "France's capital"
_POSS_RE = re.compile(
    rf"^\s*{_LEAD}(?:what|who)(?:'s|\s+is|\s+are|\s+was|\s+were)?\s+{_ART}"
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)'s\s+"
    r"(?P<rel>[A-Za-z][A-Za-z .'\-]{1,40}?)\s*[?.!]*\s*$",
    re.IGNORECASE)
_POSS_BARE_RE = re.compile(
    r"^\s*(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)'s\s+"
    r"(?P<rel>[A-Za-z][A-Za-z .'\-]{1,40}?)\s*[?.!]*\s*$",
    re.IGNORECASE)
# inverted verb: "who wrote Hamlet"
_VERB_RE = re.compile(
    rf"^\s*{_LEAD}(?:who|what)\s+(?:is\s+|was\s+|are\s+|were\s+)?"
    r"(?P<verb>[A-Za-z]+)\b\s+" + _ART +
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s*[?.!]*\s*$",
    re.IGNORECASE)
# inverted attribute: "what is <ENTITY> made of / composed of / part of / used for"
_MADEOF_RE = re.compile(
    rf"^\s*{_LEAD}what(?:'s)?(?:\s+(?:is|are|was|were))?\s+{_ART}"
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s+"
    r"(?P<rel>made\s+of|composed\s+of|made\s+up\s+of|part\s+of|used\s+for)\s*[?.!]*\s*$",
    re.IGNORECASE)

# ── S1 Wikidata coverage shapes (2026-07-24) ─────────────────────────────────────────────────
# GENERAL question phrasings for the bulk relations the store just gained. The relation-noun
# whitelist below is a LAD surface-layer relation-NAME list (the sanctioned exception), not world
# facts; grounding still comes only from a stored edge, else honest abstention.
# "what country/continent/... is <ENTITY> in/located in" -> the containment relation (VERIFIED
# defect: _subject_candidates('what country is Athens in') returned ['country'], never 'Athens').
_CONTAIN_REL = r"country|continent|region|state|province|nation|city|county|district"
_WHAT_REL_IN_RE = re.compile(
    rf"^\s*{_LEAD}(?:in\s+)?(?:what|which)\s+(?P<rel>{_CONTAIN_REL})\s+"
    r"(?:is|are|was|were|does|do)\s+" + _ART +
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s+"
    r"(?:in|on|located(?:\s+(?:in|on))?|part\s+of|situated(?:\s+in)?|found)\s*[?.!]*\s*$",
    re.IGNORECASE)
# "<ENTITY> is in which country" / "<ENTITY> is located in which continent"
_ENT_IN_WHICH_RE = re.compile(
    r"^\s*(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s+"
    r"(?:is|are|was|were)\s+(?:located\s+|situated\s+|found\s+)?in\s+which\s+"
    rf"(?P<rel>{_CONTAIN_REL})\s*[?.!]*\s*$", re.IGNORECASE)
# "where is <ENTITY>" / "where is <ENTITY> located" -> located_in
_WHERE_RE = re.compile(
    rf"^\s*{_LEAD}where\s+(?:is|are|was|were)\s+" + _ART +
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)"
    r"(?:\s+(?:located|situated|found))?\s*[?.!]*\s*$", re.IGNORECASE)
# "what does <ENTITY> do for a living" / "what is <ENTITY>'s job/profession" -> occupation.
# Checked BEFORE the capable_of "what does X do" shape cannot fire (that one ends at "do").
_LIVING_RE = re.compile(
    rf"^\s*{_LEAD}what\s+do(?:es)?\s+" + _ART +
    r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)\s+do\s+for\s+a\s+living\s*[?.!]*\s*$",
    re.IGNORECASE)

# ── R2 attribute-question shapes: capable_of / has_a / has_property ──────────────────────────
# The R2 ConceptNet densification loaded capable_of/has_a/has_property edges; these shapes let
# NATURAL phrasings ("what can a dog do", "what does a car have", "what is an apple like") reach
# them. Each row is (regex, rel_raw, rel_norm); the emitted canonical rel_norm is mapped to the
# stored predicate label by _predicate_targets. kind == "attribute" forces the relational branch
# (mirrors the used_for/made_of "verb" path); grounding comes only from a real edge, else an
# HONEST abstention — never a head-noun define. Entity is a named group; a stop-word entity
# (pronoun/self-reference) makes the row fall through to the unchanged pipeline.
_ATTR_ENT = r"(?P<entity>[A-Za-z0-9][A-Za-z0-9 .'\-]{0,60}?)"
# (regex, rel_raw, rel_norm): rel_raw is the READABLE noun shown in the abstention / certificate
# ("no grounded <rel_raw> fact for X"); rel_norm is the canonical key _predicate_targets maps to
# the stored predicate label. Grounded answers are phrased from the edge label, not rel_raw.
_ATTR_SHAPES: list[tuple[Any, str, str]] = [
    # capable_of ← "what can X do" / "what could X do"
    (re.compile(rf"^\s*{_LEAD}what\s+(?:can|could)\s+{_ART}{_ATTR_ENT}\s+do\s*[?.!]*\s*$",
                re.IGNORECASE), "capability", "capable of"),
    # capable_of ← "what is X able to do"
    (re.compile(rf"^\s*{_LEAD}what\s+(?:is|are|was|were)\s+{_ART}{_ATTR_ENT}"
                r"\s+able\s+to\s+do\s*[?.!]*\s*$", re.IGNORECASE), "capability", "capable of"),
    # capable_of ← "what does X do" / "what do X do"
    (re.compile(rf"^\s*{_LEAD}what\s+do(?:es)?\s+{_ART}{_ATTR_ENT}\s+do\s*[?.!]*\s*$",
                re.IGNORECASE), "capability", "capable of"),
    # has_a ← "what does X have" / "what do X have"
    (re.compile(rf"^\s*{_LEAD}what\s+do(?:es)?\s+{_ART}{_ATTR_ENT}\s+have\s*[?.!]*\s*$",
                re.IGNORECASE), "parts", "has a"),
    # has_a ← "what does X consist of"
    (re.compile(rf"^\s*{_LEAD}what\s+do(?:es)?\s+{_ART}{_ATTR_ENT}"
                r"\s+consists?\s+of\s*[?.!]*\s*$", re.IGNORECASE), "parts", "has a"),
    # has_a ← "what are the parts of X" / bare "parts of X"
    (re.compile(rf"^\s*{_LEAD}(?:what\s+(?:are|is)\s+the\s+)?parts\s+of\s+{_ART}{_ATTR_ENT}"
                r"\s*[?.!]*\s*$", re.IGNORECASE), "parts", "has a"),
    # has_a ← "what parts does X have"
    (re.compile(rf"^\s*{_LEAD}what\s+parts\s+do(?:es)?\s+{_ART}{_ATTR_ENT}\s+have\s*[?.!]*\s*$",
                re.IGNORECASE), "parts", "has a"),
    # has_property ← "what is X like"
    (re.compile(rf"^\s*{_LEAD}what\s+(?:is|are|was|were)\s+{_ART}{_ATTR_ENT}\s+like\s*[?.!]*\s*$",
                re.IGNORECASE), "properties", "has property"),
    # has_property ← "what properties does X have"
    (re.compile(rf"^\s*{_LEAD}what\s+(?:properties|property|qualities|characteristics|attributes)"
                rf"\s+do(?:es)?\s+{_ART}{_ATTR_ENT}\s+have\s*[?.!]*\s*$",
                re.IGNORECASE), "properties", "has property"),
    # has_property ← "what are the properties of X" / bare "properties of X"
    (re.compile(rf"^\s*{_LEAD}(?:what\s+(?:are|is)\s+the\s+)?"
                rf"(?:properties|qualities|characteristics|attributes)\s+of\s+{_ART}{_ATTR_ENT}"
                r"\s*[?.!]*\s*$", re.IGNORECASE), "properties", "has property"),
]

_STOP_ENTITY = {"", "it", "this", "that", "these", "those", "them", "there", "here",
                "you", "me", "us", "him", "her", "i", "we", "they", "he", "she",
                "everything", "anything", "something"}


def _norm_rel(rel: str) -> str:
    r = re.sub(r"\s+", " ", str(rel or "").strip().lower())
    r = re.sub(r"^(the|a|an)\s+", "", r)
    return r.strip(" .'-")


def _clean_entity(ent: str) -> str:
    e = re.sub(r"\s+", " ", str(ent or "").strip())
    e = re.sub(r"[?.!,;:]+$", "", e).strip()
    return e


def parse_relational_shape(query: str) -> dict[str, Any] | None:
    """Structurally parse a relational question into {rel, rel_norm, entity, core, kind}.

    Returns None when the query is NOT a relational shape (plain define, greeting, etc.) —
    the caller then falls through to the unchanged pipeline. Deterministic, English only
    (Korean questions are refused upstream by the English-only containment).
    """
    q = str(query or "").strip()
    if not q or re.search(r"[가-힣]", q):
        return None

    # A0) R2 attribute shapes (capable_of / has_a / has_property). Checked BEFORE the generic
    # "<REL> of <ENTITY>" arm so "parts of X" / "properties of X" resolve to has_a / has_property
    # instead of being read as a rel word "parts"/"properties". core=None (not a compound entity).
    for rx, rel_raw, rel_norm in _ATTR_SHAPES:
        m = rx.match(q)
        if m:
            entity = _clean_entity(m.group("entity"))
            if entity and entity.lower() not in _STOP_ENTITY:
                return {"rel": rel_raw, "rel_norm": rel_norm, "entity": entity,
                        "core": None, "kind": "attribute"}

    # A0b) S1 Wikidata coverage shapes: containment ("what country is X in"), inverse containment
    # ("X is in which country"), "where is X", and occupation-by-livelihood ("what does X do for a
    # living"). Checked before the generic arms so the relation NOUN is not mis-read as the subject.
    m = _LIVING_RE.match(q)
    if m:
        entity = _clean_entity(m.group("entity"))
        if entity and entity.lower() not in _STOP_ENTITY:
            return {"rel": "occupation", "rel_norm": "occupation", "entity": entity,
                    "core": None, "kind": "verb"}
    for rx in (_WHAT_REL_IN_RE, _ENT_IN_WHICH_RE):
        m = rx.match(q)
        if m:
            rel_norm = _norm_rel(m.group("rel"))
            entity = _clean_entity(m.group("entity"))
            if entity and entity.lower() not in _STOP_ENTITY:
                return {"rel": m.group("rel").strip(), "rel_norm": rel_norm, "entity": entity,
                        "core": None, "kind": "verb"}
    m = _WHERE_RE.match(q)
    if m:
        entity = _clean_entity(m.group("entity"))
        if entity and entity.lower() not in _STOP_ENTITY:
            return {"rel": "located", "rel_norm": "located", "entity": entity,
                    "core": None, "kind": "verb"}

    # A) "<REL> of <ENTITY>" (question-led, then bare "the REL of ENTITY")
    for rx in (_OF_RE, _OF_BARE_RE):
        m = rx.match(q)
        if m:
            rel_norm = _norm_rel(m.group("rel"))
            entity = _clean_entity(m.group("entity"))
            if rel_norm and entity and entity.lower() not in _STOP_ENTITY and rel_norm != "kind":
                return {"rel": m.group("rel").strip(), "rel_norm": rel_norm, "entity": entity,
                        "core": f"{rel_norm} of {entity}".lower(), "kind": "of"}

    # B) inverted attribute: "what is <ENTITY> made of"
    m = _MADEOF_RE.match(q)
    if m:
        rel_norm = _norm_rel(m.group("rel"))
        entity = _clean_entity(m.group("entity"))
        if entity and entity.lower() not in _STOP_ENTITY:
            return {"rel": m.group("rel").strip(), "rel_norm": rel_norm, "entity": entity,
                    "core": None, "kind": "verb"}

    # C) possessive: "France's capital" / "what is France's capital"
    for rx in (_POSS_RE, _POSS_BARE_RE):
        m = rx.match(q)
        if m:
            rel_norm = _norm_rel(m.group("rel"))
            entity = _clean_entity(m.group("entity"))
            if rel_norm and entity and entity.lower() not in _STOP_ENTITY:
                return {"rel": m.group("rel").strip(), "rel_norm": rel_norm, "entity": entity,
                        "core": None, "kind": "possessive"}

    # D) inverted verb: "who wrote Hamlet"
    m = _VERB_RE.match(q)
    if m:
        verb = m.group("verb").lower()
        if verb in _INVERTED_VERBS:
            entity = _clean_entity(m.group("entity"))
            if entity and entity.lower() not in _STOP_ENTITY:
                rel = _INVERTED_VERBS[verb]
                return {"rel": rel, "rel_norm": _norm_rel(rel), "entity": entity,
                        "core": None, "kind": "verb"}
    return None


# ── graph resolution ────────────────────────────────────────────────────────────────────────
def _entity_variants(entity: str) -> list[str]:
    out = [entity]
    for v in (entity.lower(), entity.title(), entity.capitalize()):
        if v not in out:
            out.append(v)
    return out


def _facts_for(entity: str, store: Any) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for v in _entity_variants(entity):
        try:
            got = store.facts_about(v, limit=60) or []
        except Exception:
            got = []
        if not got:
            try:
                from packages.graph_scale.answer_bridge import _pack_facts
                got = _pack_facts(v, limit=60) or []
            except Exception:
                got = []
        for s, p, o in got:
            key = (str(s), str(p), str(o))
            if key not in seen:
                seen.add(key)
                rows.append(key)
        if rows:
            break
    return rows


def _facts_for_preds(entity: str, preds: set[str], store: Any) -> list[tuple[str, str, str]]:
    """Predicate-SCOPED fetch: ask the store only for the wanted predicate labels. A high-degree
    subject (measured: 'cat' has 586 located_in edges) floods an unscoped limit-N fetch so the
    asked predicate (cat's 111 capable_of edges) never appears — scoping retrieves it directly.
    Falls back to [] (caller uses the unscoped path) for stores whose facts_about lacks preds=."""
    if not preds:
        return []
    preds_t = tuple(sorted(preds))
    for v in _entity_variants(entity):
        try:
            got = store.facts_about(v, limit=60, preds=preds_t) or []
        except TypeError:
            return []  # store/double without preds support — let the caller use _facts_for
        except Exception:
            got = []
        rows: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for s, p, o in got:
            key = (str(s), str(p), str(o))
            if key not in seen and str(o).strip():
                seen.add(key)
                rows.append(key)
        if rows:
            return rows
    return []


def _wanted_labels(rel_norm: str) -> set[str]:
    """The stored predicate labels that answer the asked relation (surface synonyms + the
    underscored rel_norm itself). Used both to MATCH edges and to predicate-SCOPE the fetch."""
    wanted = set(REL_SYNONYMS.get(rel_norm, frozenset()))
    wanted.add(rel_norm.replace(" ", "_"))
    return wanted


# ── precision gate (2026-07-24): consensus resolution over cross-linked bulk edges ──────────────
# The 115M Wikidata ingest carries CROSS-LINK NOISE: one subject often holds several conflicting
# targets on a SINGLE-VALUED relation (VERIFIED on seal_knowledge_holdout: 'Athens' country =
# {United States, Greece, United Kingdom}; 'Baku' country = {Japan, Ghana, Zimbabwe}). The old
# resolver returned targets[0] in stored order — a coin-flip that produced a 30% wrong-answer rate
# (127/421). These sets are a relation-PROPERTY list (single-valued vs multi-valued), the LAD
# surface layer, NOT world facts.
_FUNCTIONAL_RELS: frozenset[str] = frozenset({
    "capital", "capital city", "country", "located country", "located", "located in", "location",
    "continent", "currency", "population", "area", "boiling point", "melting point",
    "atomic number", "atomic mass", "density", "father", "mother", "birthplace",
    "birth date", "date of birth", "date of death",
})
# Broad containment predicates: a city's located_in returns admin subregions (districts/counties),
# a country's returns a continent — acceptable ONLY as a fallback proxy when no native predicate
# exists (e.g. 'continent' has no native store label). A native label always wins.
_BROAD_PROXY_LABELS: frozenset[str] = frozenset({"located_in", "location", "part_of"})


def _predicate_targets(rel_norm: str, facts: list[tuple[str, str, str]],
                       entity: str = "") -> tuple[str, list[str]]:
    """Resolve the edge that answers the asked relation -> (edge_label, targets).

    Groups the matched-edge objects by predicate label (with multiplicity across the synonym set).
    Then, for a FUNCTIONAL (single-valued) relation, this is the PRECISION GATE:
      * prefer NATIVE labels (exact predicate) over broad containment proxies;
      * over the chosen tier, take the STRICTLY most-supported target — a target corroborated by
        more edges (e.g. Austria's continent 'Europe' appears via both part_of AND located_in,
        while every noise target appears once) wins cleanly;
      * a TIE for top support means the store contradicts itself about a single-valued fact — the
        entity match is AMBIGUOUS, so return no target (the caller then HONEST-ABSTAINS) rather
        than guessing. This trades coverage for precision on exactly the cross-linked cases.
    A multi-valued relation (occupation, genre, capable_of, ...) keeps its several targets — many
    objects is NORMAL there, not a contradiction. Answers still come only from stored edges."""
    wanted = _wanted_labels(rel_norm)
    by_label: dict[str, Counter] = {}
    for _s, p, o in facts:
        if p in ("alias", "sense") or not str(o).strip():
            continue
        if p in wanted or p.replace(" ", "_") == rel_norm.replace(" ", "_"):
            by_label.setdefault(p, Counter())[str(o)] += 1
    if not by_label:
        return "", []

    def _merge(labels: dict[str, Counter]) -> tuple[Counter, dict[str, str]]:
        merged: Counter = Counter()
        label_of: dict[str, str] = {}
        for lab, cnt in labels.items():
            for tgt, n in cnt.items():
                merged[tgt] += n
                label_of.setdefault(tgt, lab)
        return merged, label_of

    if rel_norm in _FUNCTIONAL_RELS:
        native = {l: c for l, c in by_label.items() if l not in _BROAD_PROXY_LABELS}
        merged, label_of = _merge(native or by_label)
        ranked = merged.most_common()
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            pick = ranked[0][0]
            return label_of[pick], [pick]
        # AMBIGUOUS single-valued fact. Abstaining here is right, but abstaining SILENTLY meant
        # walking into the same wall on every future ask. This tie is ATANOR noticing that its own
        # knowledge is merged -- the label-keyed ingest put several referents on one node -- so the
        # sighting goes to the conflict ledger, ranked later by how often it actually blocks an
        # answer. Recording only; nothing here picks a winner, because the evidence that would
        # settle it is not in the graph.
        try:
            from packages.knowledge_repair.conflict_ledger import record_conflict
            record_conflict(entity, rel_norm, [t for t, _ in ranked],
                            source="relational_lookup.precision_gate")
        except Exception:
            pass
        return "", []                      # ambiguous single-valued fact -> abstain

    merged, label_of = _merge(by_label)
    top = [tgt for tgt, _ in merged.most_common(3)]
    return (label_of[top[0]], top) if top else ("", [])


def _entity_is_grounded(entity: str, store: Any) -> bool:
    facts = _facts_for(entity, store)
    return any(p not in ("alias", "sense") for (_s, p, _o) in facts)


def _compound_is_grounded(core: str | None, store: Any) -> bool:
    """The whole 'X of Y' phrase has its OWN substantive define -> it is a compound ENTITY
    (speed of light), not a relation over a distinct entity (capital of France)."""
    if not core:
        return False
    facts = _facts_for(core, store)
    return any(p in ("defined_as", "is_a") and str(o).strip()
               for (_s, p, o) in facts)


# ── fictional-subject precision gate (2026-07-24) ────────────────────────────────────────────
# A real-world GEO/political attribute (capital, country, continent, currency, ...) presupposes a
# real-world referent. The 115M store carries in-universe facts for fictional places as first-class
# edges STRUCTURALLY IDENTICAL to real ones (VERIFIED: Wakanda capital=Birnin Zana, Gondor
# capital=Minas Tirith — clean single edges, just like France capital=Paris). Answering those as
# plain real-world facts is a soft-hallucination for a factual question. This gate reads the
# subject's graph is_a: if it is marked FICTIONAL with NO competing real-PLACE type, a geo-attribute
# ask ABSTAINS (honestly noting the entity is fictional). GRAPH-GROUNDED (reads is_a, no entity
# list) and GENERAL (catches Wakanda/Gondor/Zamunda alike). The relation set is the LAD surface
# layer. Real entities that merely carry a stray 'fictional …' pollution edge (VERIFIED: Russia,
# Vienna, Sarajevo each is_a a fictional character too) are SPARED by the real-place-type test, so
# the 275 geo subjects of the seal holdout are untouched (measured: 0 gated).
_REALWORLD_GEO_RELS: frozenset[str] = frozenset({
    "capital", "capital city", "country", "located country", "located", "located in", "location",
    "continent", "currency", "population", "area", "official language", "national language",
    "national anthem", "time zone", "gdp",
})
_FICTIONAL_RE = re.compile(r"\bfictional\b", re.IGNORECASE)
_REAL_PLACE_RE = re.compile(
    r"\b(countr(?:y|ies)|sovereign\s+state|nation|state|city|cities|big\s+city|megacity|"
    r"metropolis|town|municipalit(?:y|ies)|commune|human\s+settlement|settlement|province|"
    r"county|region|village|capital|port\s+city|republic|kingdom|empire|federation|prefecture|"
    r"district|island|department|territory|autonomous)\b", re.IGNORECASE)


def _is_fictional_geo_subject(entity: str, store: Any) -> bool:
    """True when the subject's graph is_a marks it FICTIONAL with no competing real-place type.
    Reads only the is_a edges (predicate-scoped) so a software/character homonym never spares a
    fictional PLACE (VERIFIED: Wakanda is_a {fictional country, proprietary software, …} -> True)."""
    if store is None or not entity:
        return False
    facts = _facts_for_preds(entity, {"is_a"}, store)
    if not facts:
        facts = [f for f in _facts_for(entity, store) if f[1] == "is_a"]
    isa = [str(o) for (_s, p, o) in facts if p == "is_a" and str(o).strip()]
    if not any(_FICTIONAL_RE.search(v) for v in isa):
        return False
    has_real_place = any(_REAL_PLACE_RE.search(v) and not _FICTIONAL_RE.search(v) for v in isa)
    return not has_real_place


def _phrase(entity: str, edge: str, rel_raw: str, targets: list[str]) -> str:
    ent = entity[:1].upper() + entity[1:] if entity else entity
    joined = targets[0] if len(targets) == 1 else (
        ", ".join(targets[:-1]) + " and " + targets[-1])
    if edge in ("made_of", "composed_of", "material"):
        return f"{ent} is made of {joined}."
    if edge == "part_of":
        return f"{ent} is part of {targets[0]}."
    if edge == "used_for":
        return f"{ent} is used for {joined}."
    if edge == "capable_of":
        return f"{ent} can {joined}."
    if edge in ("has_a", "has_part"):
        return f"{ent} has {joined}."
    if edge == "has_property":
        return f"{ent} is {joined}."
    if edge in ("located_in", "location"):
        return f"{ent} is located in {targets[0]}."
    if edge in ("capital", "capital_city"):
        return f"The capital of {entity} is {targets[0]}."
    if edge in ("country", "located_country"):
        return f"{ent} is in {targets[0]}."
    if edge == "occupation":
        return f"{ent}'s occupation is {joined}."
    if edge == "genre":
        return f"{ent}'s genre is {joined}."
    if edge in ("manufacturer", "made_by", "maker"):
        return f"{ent} is made by {targets[0]}."
    if edge in ("employer", "employed_by"):
        return f"{ent} works for {targets[0]}."
    if edge == "sport":
        return f"{ent}'s sport is {joined}."
    if edge == "religion":
        return f"{ent}'s religion is {joined}."
    if edge in ("director", "directed_by"):
        return f"{ent} was directed by {targets[0]}."
    if edge in ("official_language", "language"):
        return f"The official language of {entity} is {joined}."
    if edge in ("author", "written_by", "creator", "writer", "composed_by", "composer"):
        return f"{ent} is by {targets[0]}."
    return f"The {_norm_rel(rel_raw)} of {entity} is {joined}."


def _forward_edge_answer(shape: dict[str, Any], store: Any) -> dict[str, Any] | None:
    entity, rel_norm, rel_raw = shape["entity"], shape["rel_norm"], shape["rel"]
    # Predicate-SCOPED fetch first (avoids the high-degree flood, e.g. cat's 586 located_in edges
    # burying its 111 capable_of edges past the fetch limit); fall back to the unscoped fetch so
    # nothing that grounded before can stop grounding. Monotonic: only ever ADDS groundings, and
    # every returned target is still a real stored edge (no fabrication).
    facts = _facts_for_preds(entity, _wanted_labels(rel_norm), store)
    if not facts:
        facts = _facts_for(entity, store)
    if not facts:
        return None
    edge, targets = _predicate_targets(rel_norm, facts, entity)
    if not edge or not targets:
        return None
    answer = _phrase(entity, edge, rel_raw, targets)
    cert = {
        "derivation_kind": "relational_edge_lookup",
        "anchor_concept": {"label": entity},
        "edge": edge,
        "asked_relation": _norm_rel(rel_raw),
        "steps": [{"type": "triple", "fact": f"{entity} {edge} {t}"} for t in targets],
        "evidence_concepts": [entity, *targets],
        "confidence": 0.9,
        "confidence_basis": "curated_structured_triple_verbatim "
                            "(entity edge label matches the asked relation)",
        "guarantees": {"external_llm": False, "fabricated_facts": False,
                       "inferred": False, "verified": True},
    }
    return {"answer": answer, "reasoning_certificate": cert, "confidence": 0.9,
            "answer_kind": "relational_edge_lookup", "intent": "relational",
            "relational": {"rel": _norm_rel(rel_raw), "entity": entity,
                           "edge": edge, "resolved": True}}


def _honest_abstain(shape: dict[str, Any], entity_grounded: bool) -> dict[str, Any]:
    entity, rel_raw = shape["entity"], _norm_rel(shape["rel"])
    basis = ("the entity is in my graph but carries no edge for the asked relation"
             if entity_grounded else "I have no grounded record for that entity")
    return {
        "answer": f"I don't hold a grounded {rel_raw} fact for {entity} yet.",
        "reasoning_certificate": {
            "derivation_kind": "relational_abstention",
            "anchor_concept": {"label": entity},
            "asked_relation": rel_raw,
            "steps": [{"type": "gap",
                       "fact": f"no '{rel_raw}' edge on '{entity}' in the graph"}],
            "evidence_concepts": [entity],
            "confidence": 0.2,
            "confidence_basis": basis + "; abstained rather than defining the head noun",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "verified": True},
        },
        "confidence": 0.2,
        "answer_kind": "honest_abstain_relational",
        "intent": "relational",
        "relational": {"rel": rel_raw, "entity": entity, "edge": None, "resolved": False},
    }


def _fictional_abstain(shape: dict[str, Any]) -> dict[str, Any]:
    """Abstention for a real-world GEO attribute asked of a graph-marked FICTIONAL subject: the
    entity has in-universe edges but no real-world referent, so a plain factual answer would state
    an in-universe fact as real. Confidence 0.2, honestly labeled — never the in-universe value."""
    entity, rel_raw = shape["entity"], _norm_rel(shape["rel"])
    return {
        "answer": (f"{entity} appears to be a fictional entity, so I don't hold a real-world "
                   f"{rel_raw} for it."),
        "reasoning_certificate": {
            "derivation_kind": "relational_abstention",
            "anchor_concept": {"label": entity},
            "asked_relation": rel_raw,
            "steps": [{"type": "gap",
                       "fact": f"'{entity}' is_a fictional entity in the graph; a real-world "
                               f"'{rel_raw}' is not defined for it"}],
            "evidence_concepts": [entity],
            "confidence": 0.2,
            "confidence_basis": "subject is graph-marked fictional with no real-place referent; "
                                "abstained rather than voicing an in-universe fact as real",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "verified": True},
        },
        "confidence": 0.2,
        "answer_kind": "honest_abstain_relational",
        "intent": "relational",
        "relational": {"rel": rel_raw, "entity": entity, "edge": None, "resolved": False},
    }


def _compound_define(query: str, language: str) -> dict[str, Any] | None:
    """A grounded compound entity ('speed of light') is defined AS THE COMPOUND via the
    existing graph bridge — never decomposed to the head noun."""
    try:
        from packages.graph_scale.answer_bridge import answer_from_triples
        b = answer_from_triples(query, language)
    except Exception:
        b = None
    if not b:
        return None
    ans = str(b.get("answer") or "")
    if not ans or re.search(r"[가-힣]", ans):
        return None
    out = dict(b)
    out["intent"] = "define"
    return out


def resolve_relational(query: str, language: str = "en", store: Any | None = None
                       ) -> dict[str, Any] | None:
    """The relational lane. Returns a core answer dict (answer, reasoning_certificate,
    confidence, answer_kind, intent, relational) or None when the query is not a relational
    shape (fall through to the unchanged define pipeline).

    English-only: Korean input is refused upstream, and resolve_relational returns None for it.
    """
    if str(language or "").lower().startswith("ko"):
        return None
    query = _normalize_query(query)              # entry robustness: de-obfuscate before parsing
    shape = parse_relational_shape(query)
    if not shape:
        return None

    # Defer entities that carry a temporal qualifier or a number ("Mars in 2099", "France
    # today"): those are not clean lookup entities — the realtime / structurally-unanswerable
    # lanes already own them, and echoing the qualifier back in an abstention would surface a
    # spurious figure. Clean entities (France, water, Hamlet) pass straight through.
    if re.search(r"\d|\b(today|now|current|currently|latest|tonight|tomorrow|yesterday|"
                 r"this\s+year|last\s+year|next\s+year)\b", shape["entity"], re.IGNORECASE):
        return None

    if store is None:
        try:
            from packages.graph_scale.answer_bridge import _store
            store = _store()
        except Exception:
            store = None

    # 1) grounded COMPOUND entity ("speed of light") -> define the compound, not the head noun.
    if store is not None and _compound_is_grounded(shape.get("core"), store):
        comp = _compound_define(query, language)
        if comp is not None:
            return comp

    # 1.5) FICTIONAL-subject gate: a real-world GEO attribute (capital/country/continent/...) asked
    #      of a graph-marked fictional place has no real-world answer, only an in-universe edge —
    #      abstain rather than voice "The capital of Wakanda is Birnin Zana" as a plain fact.
    if (store is not None and shape["rel_norm"] in _REALWORLD_GEO_RELS
            and _is_fictional_geo_subject(shape["entity"], store)):
        return _fictional_abstain(shape)

    # 2) learned gate: define-vs-relational. Relation-vocab membership and the inverted-verb
    #    shape hard-force the relational branch (the measured defect family); otherwise the
    #    trained scorer decides.
    forced = answerable_relation(shape["rel_norm"]) or (shape["kind"] in ("verb", "attribute"))
    is_relational = forced
    if not forced:
        try:
            from .relational_router import RelationalRouter
            cls, _prob = RelationalRouter.load().classify(query)
            is_relational = (cls == "relational")
        except Exception:
            is_relational = False

    if not is_relational:
        # scorer says this is a definition and it is not a grounded compound -> leave the
        # existing pipeline untouched (no regression on plain/loose defines).
        return None

    # 3) resolve by GRAPH: the entity's edge that matches the asked relation, else honest abstain.
    if store is not None:
        ans = _forward_edge_answer(shape, store)
        if ans is not None:
            return ans
        grounded = _entity_is_grounded(shape["entity"], store)
    else:
        grounded = False
    return _honest_abstain(shape, grounded)
