# -*- coding: utf-8 -*-
"""Polysemy hub splitting — the reasoning core's named next bottleneck.

THE PROBLEM: one term node conflates every sense of the word. holds both
" " (emotion) and " "
(a room in a traditional house). Multihop reasoning walks through the hub and
crosses senses — an inference about love arrives at architecture. Every
composition built on such a hub silently corrupts.

THE ARCHITECTURE (graph-derived VIEW, never a rule table):
 * induce_senses(term) — cluster the term's own definition rows by shared
 content words (two defs describe one sense iff their content vocabularies
 overlap). Each cluster = a sense with a signature (its content-word set)
 and a gloss (its shortest definition). One cluster -> monosemous, no split.
 * resolve_sense(term, context) — the query's own content words vote against
 each sense signature (direct overlap first, trained phase-space resonance
 as the graded fallback), returning the sense the CONTEXT means.
 * sense_filtered_facts(term, context, rows) — the practical hook: given the
 term's fact rows, keep the ones belonging to the resolved sense, so a
 definitional answer about () never surfaces the sense.

Senses are derived from the graph's own definitions at call time — nothing is
authored, nothing persists outside the graph, and a graph with better
definitions immediately yields better senses (density thesis).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CONTENT = re.compile(r"[가-힣]{2,}")
_JOSA_TAIL = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|이나|나)$")
# generic definitional scaffolding that appears in EVERY dictionary gloss and
# therefore carries no sense signal (measured from the store's own prose)
_SCAFFOLD = {"또는", "그런", "따위", "어떤", "무엇", "하는", "있는", "되는", "위해",
             "통해", "대한", "가장", "함께", "이르는", "부르는", "지칭하는"}

_MIN_SHARED = 2       # defs sharing >= this many content words merge into one sense
_MIN_JACCARD = 0.25   # or overlapping by this fraction (short-gloss friendly)


def content_words(text: str, limit: int = 24) -> list[str]:
    out: list[str] = []
    for tok in _CONTENT.findall(str(text or "")):
        base = _JOSA_TAIL.sub("", tok)
        if len(base) >= 2 and base not in _SCAFFOLD and base not in out:
            out.append(base)
        if len(out) >= limit:
            break
    return out


@dataclass
class Sense:
    sense_id: str
    gloss: str
    signature: set[str] = field(default_factory=set)
    definitions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"sense_id": self.sense_id, "gloss": self.gloss,
                "signature": sorted(self.signature),
                "definitions": self.definitions}


def _overlaps(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    shared = len(a & b)
    if shared >= _MIN_SHARED:
        return True
    return shared / min(len(a), len(b)) >= _MIN_JACCARD if shared else False


def induce_senses(term: str, definitions: list[str] | None = None) -> list[Sense]:
    """Cluster the term's definition rows into senses. Pass definitions
    explicitly for tests; default reads the live KG."""
    if definitions is None:
        definitions = _kg_definitions(term)
    defs = [d for d in (str(x).strip() for x in definitions) if len(d) >= 6]
    if not defs:
        return []
    # greedy agglomerative merge on content-word overlap (defs per term are
    # few — this is O(n^2) over n<20, essentially free)
    clusters: list[tuple[set[str], list[str]]] = []
    for d in defs:
        words = set(content_words(d))
        home = None
        for sig, members in clusters:
            if _overlaps(sig, words):
                home = (sig, members)
                break
        if home is None:
            clusters.append((words, [d]))
        else:
            home[0].update(words)
            home[1].append(d)
    # second pass: merging may have made two clusters overlap transitively
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if _overlaps(clusters[i][0], clusters[j][0]):
                    clusters[i][0].update(clusters[j][0])
                    clusters[i][1].extend(clusters[j][1])
                    del clusters[j]
                    merged = True
                    break
            if merged:
                break
    senses = []
    for i, (sig, members) in enumerate(clusters):
        gloss = min(members, key=len)
        senses.append(Sense(sense_id=f"{term}#{i}", gloss=gloss,
                            signature=sig, definitions=members))
    # dominant sense first: the one the graph describes the most
    senses.sort(key=lambda s: -len(s.definitions))
    return senses


def _kg_definitions(term: str) -> list[str]:
    try:
        from .answer_bridge import _store

        kg = _store()
        if kg is None:
            return []
        rows = kg.facts_with_sources(term, limit=24, preds=("defined_as", "is_a")) or []
        return [str(r[2]) for r in rows if len(r) > 2]
    except Exception:
        return []


def resolve_sense(term: str, context: str,
                  senses: list[Sense] | None = None) -> Sense | None:
    """Which sense does THIS context mean? Direct content-word overlap votes
    first; the trained phase space breaks ties as a graded signal. A context
    with no signal returns the dominant sense (honest default, never random)."""
    if senses is None:
        senses = induce_senses(term)
    if not senses:
        return None
    if len(senses) == 1:
        return senses[0]
    ctx_words = [w for w in content_words(context) if w != term]
    if ctx_words:
        # tier 1: the context's own words vote directly
        best, best_score = _vote(ctx_words, senses)
        if best is not None and best_score > 0:
            return best
        # tier 2 (graph-native): expand context words through THEIR definitions —

        # lands squarely in the house sense's signature
        expanded: list[str] = []
        for w in ctx_words[:3]:
            for d in _kg_definitions(w)[:3]:
                expanded.extend(x for x in content_words(d, limit=10) if x != term)
        if expanded:
            best, best_score = _vote(expanded, senses)
            if best is not None and best_score > 0:
                return best
        # tier 3: trained phase-space resonance as the graded fallback
        best, best_score = None, 0.0
        for s in senses:
            try:
                from .phase_space import resonance

                vals = [r for w in ctx_words[:4] for g in list(s.signature)[:6]
                        if (r := resonance(w, g)) is not None]
                score = max(vals) if vals else 0.0
            except Exception:
                score = 0.0
            if score > best_score:
                best, best_score = s, score
        if best is not None and best_score > 0.3:
            return best
    return senses[0]  # dominant sense — the graph's own prior


def _vote(words: list[str], senses: list[Sense]) -> tuple[Sense | None, float]:
    best, best_score = None, 0.0
    for s in senses:
        score = sum(1.0 for w in words if w in s.signature)
        if score > best_score:
            best, best_score = s, score
    return best, best_score


def sense_filtered_facts(term: str, context: str,
                         rows: list[tuple], *,
                         senses: list[Sense] | None = None) -> list[tuple]:
    """The answer-path hook: keep the fact rows whose OBJECT text belongs to
    the resolved sense (definition rows of other senses drop). Non-definition
    rows pass through untouched — only the polysemous prose is disambiguated."""
    if senses is None:
        senses = induce_senses(term)
    if len(senses) <= 1:
        return rows
    chosen = resolve_sense(term, context, senses=senses)
    if chosen is None:
        return rows
    chosen_defs = set(chosen.definitions)
    other_defs: set[str] = set()
    for s in senses:
        if s.sense_id != chosen.sense_id:
            other_defs.update(s.definitions)
    out = []
    for row in rows:
        o = str(row[2]) if len(row) > 2 else ""
        if o in other_defs and o not in chosen_defs:
            continue
        out.append(row)
    return out


def polysemy_report(term: str) -> dict[str, Any]:
    """Inspection surface: is this term a polysemy hub, and what are its senses?"""
    senses = induce_senses(term)
    return {
        "term": term,
        "polysemous": len(senses) > 1,
        "sense_count": len(senses),
        "senses": [s.to_dict() for s in senses],
    }
