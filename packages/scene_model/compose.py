# -*- coding: utf-8 -*-
"""Compose an utterance into a Scene — the step that makes the algebra reachable from language.

The division of labour is the whole design, and it is what keeps this from becoming the 20th regex
lane:

  * WHAT the question is about -- the type, the entity, the relation -- is resolved against the
    GRAPH at parse time. `countries` is a type because its extension has members; `France` is an
    entity because the store interned it; `capital` is a relation because the predicate column
    contains it. None of those words appear in this file or in its data.
  * HOW the scene is read -- negated, counted, listed -- comes from a closed class of English
    function words in data/scene_model/markers.json, seeded and documented as a training wheel
    with a per-entry removal criterion.

So a question about a subject ATANOR has never heard of composes exactly as well as one about
France, which is the property a lane per shape can never have. A question phrased in a construction
the seed cannot see returns None WITH the reason, and the caller logs it as curriculum instead of
dropping it silently -- an unparsed question is data about what to learn next, not a failure to
hide.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from packages.scene_model.scene import Condition, Scene

_MARKERS_PATH = Path(__file__).resolve().parents[2] / "data" / "scene_model" / "markers.json"


@lru_cache(maxsize=1)
def markers() -> dict[str, Any]:
    try:
        return json.loads(_MARKERS_PATH.read_text(encoding="utf-8"))
    except Exception:                                     # missing seed => compose nothing, ever
        return {"negation": [], "readout": {}, "stop_head": [], "plural_suffixes": []}


def _toks(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def _forms(word: str) -> list[str]:
    """Surface variants to try. Morphology and orthography, never vocabulary.

    Capitalisation is here for a measured reason: the store holds two parallel populations under
    one type -- Wikidata entities capitalised, ConceptNet concepts lowercase -- and asserts no
    identity between them. Tokenising to lowercase therefore threw away the richer reading:
    `france` carries 10 edges, `France` 116, and head selection picked the determiner `the` (53)
    over the country. Trying both forms is not a guess about which is right; it is refusing to
    let the tokenizer decide a question the graph should answer."""
    out, seen = [], set()
    for base in (word, word.title()):
        cands = [base]
        for rule in markers().get("plural_suffixes", []):
            if "->" in rule:
                suf, rep = rule.split("->", 1)
                if base.endswith(suf):
                    cands.append(base[: -len(suf)] + rep)
            elif base.endswith(rule) and len(base) > len(rule) + 1:
                cands.append(base[: -len(rule)])
        for c in cands:
            for form in (c, c.replace(" ", "_")):          # the store interns `atanor_organ`
                if form not in seen:
                    seen.add(form)
                    out.append(form)
    return out


def _relation_spans(tokens: list[str], store: Any) -> list[tuple[frozenset[str], int, int]]:
    """Every token span the GRAPH recognises, with the PREDICATES it resolves to.

    Returns the resolved predicate labels, not the surface span: the evaluator looks its predicate
    up as an interned term, so handing it `"capital city"` finds nothing while the span in fact
    resolves to the real predicate `capital`. Which of several resolutions is meant is decided
    later, by coverage on the actual head -- evidence, not span length."""
    from packages.base_brain.relational_lookup import _wanted_labels, graph_relations
    live = graph_relations(store)
    if not live:
        return []
    lemmas = markers().get("verb_lemmas", {})

    def scan(loose: bool) -> list[tuple[frozenset[str], int, int, bool]]:
        out = []
        for width in range(min(3, len(tokens)), 0, -1):
            for i in range(len(tokens) - width + 1):
                span = tokens[i:i + width]
                hit = _wanted_labels(" ".join(span)) & live
                if loose:
                    # Morphology and dropped determiners: the label is `has_a`, the question says
                    # "organs HAVE no tests". Only reached when nothing named a relation exactly.
                    lem = " ".join(lemmas.get(t, t) for t in span)
                    hit |= _wanted_labels(lem) & live
                    for v in {" ".join(span), lem}:
                        vt = v.split()
                        hit |= {r for r in live if r.split("_")[:len(vt)] == vt}
                if hit:
                    aux = all(t in lemmas or t in set(lemmas.values()) for t in span)
                    out.append((frozenset(hit), i, i + width, not aux))
        return out

    # A LADDER, not a wider net. Widening the main path was measured to destroy every answer that
    # previously worked: with `is`->`is_a` and `have`->`has_a` in play, and selection maximising
    # coverage, the winner was always `is_a` -- which every member of every type carries, so it
    # discriminates nothing. "Which countries have no capital city?" became 8115 cities. Loose
    # matching is a fallback for questions nothing else can read, never a competitor to a question
    # that names its relation outright.
    return scan(loose=False) or scan(loose=True)


def _head(tokens: list[str], store: Any, skip: set[int] | None = None,
          top_k: int = 6) -> list[tuple[str, bool, int, int]]:
    """The head term and whether it is a TYPE. Both decided by the graph, never by a list.

    `skip` must cover every index already consumed as a function word or as the relation. Without
    it the interrogative wins: `which`, `what` and `how` are ordinary English words that the graph
    holds, so the first measured run bound `entity='which'` and evaluated a scene about the
    pronoun. Function words are marked in the seed precisely so they can be excluded here."""
    from packages.scene_model.evaluate import _id, extension
    stop = set(markers().get("stop_head", []))
    skip = skip or set()
    found: list[tuple[float, str, bool, int, int]] = []
    for i, tok in enumerate(tokens):
        if i in skip or tok in stop or len(tok) < 2:
            continue
        for width in (3, 2, 1):                            # prefer the longest grounded phrase
            if i + width > len(tokens) or (set(range(i, i + width)) & skip):
                continue
            for form in _forms(" ".join(tokens[i:i + width])):
                # How much does the graph know about this term AS a type, and AS a thing? The
                # larger reading wins. This is why `the`, `of` and `is` need not be listed as
                # stop words: they are real English terms the store holds, but `France` outweighs
                # them by orders of magnitude, and `country` (372 members) outweighs the stray
                # `countries` node (1). Evidence decides, so the seed never has to grow.
                as_type = len(extension(store, form))
                as_thing = 0
                if _id(store, form) is not None:
                    try:
                        as_thing = len(store.facts_about(form, limit=200))
                    except Exception:
                        as_thing = 1
                score = max(as_type, as_thing)
                if score:
                    found.append((score, form, as_type >= as_thing, i, i + width))
    # Ranked, not argmax: raw degree cannot pick the head on its own, because a frequent function
    # word can outrank the subject. Measured on "what is the capital of France?" -- `of` outscores
    # `France` (116 edges), so a single-best head bound `of` and every pairing scored 0. The caller
    # re-ranks these by how well each HEAD fits each RELATION; degree only orders the shortlist.
    found.sort(key=lambda c: -c[0])
    return [c[1:] for c in found[:top_k]]


def _dropped_qualifiers(tokens: list[str], store: Any, consumed: set[int]) -> tuple[str, ...]:
    """Grounded content words the composer recognised but had nowhere to bind.

    Not a keyword list -- a general check run on whatever is left over. Scene has exactly one
    var_type/entity slot, so a qualifying possessor or modifier ("ATANOR organs", "France's
    cities") that would need a second hop is silently dropped by construction. Measured
    2026-07-28: without this, "which atanor organs have no tests" ignored "atanor" entirely and
    answered, confidently, about human anatomy organs -- a ConceptNet homonym of the intended
    type. The caller reads a non-empty result here to abstain rather than answer a narrower,
    unintended question with confidence.

    Deliberately requires a RELATIONAL fact, not merely a dictionary gloss: ConceptNet gives
    almost every English word a `defined_as` entry, which would make ordinary function words
    ("a", "is", "have") false-positive as dropped content and abstain on questions that actually
    compose fine."""
    from packages.scene_model.evaluate import _id, extension
    stop = set(markers().get("stop_head", []))
    negators = set(markers().get("negation", []))
    lemmas = markers().get("verb_lemmas", {})
    aux = set(lemmas) | set(lemmas.values())
    dropped = []
    for i, tok in enumerate(tokens):
        if i in consumed or tok in stop or tok in negators or tok in aux or len(tok) < 3:
            continue
        for form in _forms(tok):
            if len(extension(store, form)):
                dropped.append(tok)
                break
            if _id(store, form) is not None:
                try:
                    facts = store.facts_about(form, limit=50)
                except Exception:
                    facts = []
                if any(f[1] != "defined_as" for f in facts):
                    dropped.append(tok)
                    break
    return tuple(dropped)


def compose(text: str, store: Any) -> tuple[Scene | None, str]:
    """(Scene, "") when the utterance composes; (None, reason) when it does not.

    The reason is returned rather than logged here so the caller decides what to do with it; it is
    the curriculum signal, and swallowing it would hide exactly what we need to see."""
    tokens = _toks(text)
    if not tokens:
        return None, "empty utterance"
    m = markers()
    joined = " ".join(tokens)

    readout, consumed = "", set()
    for kind, cues in (m.get("readout") or {}).items():
        hit = next((c for c in cues if c in joined), None)
        if hit:
            readout = kind
            cue = hit.split()
            for i in range(len(tokens) - len(cue) + 1):    # the cue words are not the subject
                if tokens[i:i + len(cue)] == cue:
                    consumed.update(range(i, i + len(cue)))
            break
    if not readout:
        return None, "no readout marker (not a question this composer can read)"

    negators = set(m.get("negation", []))
    negated = bool(set(tokens) & negators)
    consumed.update(i for i, t in enumerate(tokens) if t in negators)

    spans = _relation_spans(tokens, store)
    if not spans:
        return None, "no span of this question names a relation the graph uses"

    # Which (relation, head) pair the utterance means is settled by the graph, not by word order
    # or span length: score every pairing by how many of the head's peers actually carry the
    # relation. `capital city` and `capital` both resolve to {capital, capital_of}; only `capital`
    # has any country behind it (214 vs 0), so the graph picks.
    import numpy as np

    from packages.scene_model.evaluate import _id, extension, project
    best, seen_any = None, False
    for preds, lo, hi, content in spans:
        used = consumed | set(range(lo, hi))
        for rank, (term, is_type, h_lo, h_hi) in enumerate(_head(tokens, store, skip=used)):
            seen_any = True
            if is_type:
                members = extension(store, term)
            else:                              # an entity carries its own evidence: does IT have it
                eid = _id(store, term)
                members = np.array([eid], dtype="<i4") if eid is not None else np.zeros(0, "<i4")
            for pred in sorted(preds):
                # (coverage, then shortlist rank) — a pairing the graph actually supports beats a
                # more frequent word that supports nothing.
                key = (len(project(store, members, pred)), content, -rank)
                if best is None or key > best[0]:
                    best = (key, pred, term, is_type, used | set(range(h_lo, h_hi)))
    if best is None:
        return None, ("no span of this question names a type or entity the graph holds"
                      if not seen_any else "nothing in this question pairs with a relation")
    _key, rel_label, term, is_type, consumed = best

    if is_type:
        # A second grounded thing beside the relation is what the relation points AT:
        # "which cities are located in Japan" -> located_in = Japan, not located_in anything.
        # Bind it only if some member ACTUALLY holds the relation to it. Without that gate a
        # leftover function word wins: "which countries have no capital city" bound obj='have',
        # which nothing has, so the complement returned all 377 countries and looked like an
        # answer. An object no member carries is not what the question meant.
        cands = [c for c in _head(tokens, store, skip=consumed) if not c[1]]
        obj_label = cands[0][0] if cands else None
        if obj_label and not len(project(store, extension(store, term), rel_label, obj_label)):
            obj_label = None
        elif obj_label:
            consumed = consumed | set(range(cands[0][2], cands[0][3]))
        dropped = _dropped_qualifiers(tokens, store, consumed)
        return Scene(var_type=term,
                     conditions=(Condition(rel_label, obj=obj_label, negated=negated),),
                     readout="count" if readout == "count" else
                             ("exist" if readout == "exist" else "set"),
                     dropped_qualifiers=dropped), ""
    # A named entity with a relation asked of it: the answer is the relation's values, and a
    # negated form is a yes/no about possession rather than a set.
    dropped = _dropped_qualifiers(tokens, store, consumed)
    if negated:
        return Scene(entity=term, conditions=(Condition(rel_label, negated=True),),
                     readout="exist", dropped_qualifiers=dropped), ""
    return Scene(entity=term, readout="values", readout_predicate=rel_label,
                dropped_qualifiers=dropped), ""
