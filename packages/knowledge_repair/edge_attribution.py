# -*- coding: utf-8 -*-
"""A1b — place the edges A1a's referents could not, and separate "unknown" from "not this word".

Designed from a measurement, not a guess. After A1a placed 12 of 147 edges on `Athens`, the 135
that remained fell into three kinds, and they need three different treatments:

  1. EDGES THAT NAME A REFERENT NOBODY ACQUIRED. `defined_as` lists Athenses in Arkansas,
     Illinois, Kentucky, Louisiana, Maine, Michigan, Missouri, Nevada, New York, Pennsylvania,
     Tennessee, Vermont, West Virginia, Wisconsin... A1a proposed six because it required two
     sources; the graph itself is a source, and these edges ARE a referent list.
  2. EDGES OF A KNOWN REFERENT WHOSE MARKER IS NOT IN THE OBJECT TEXT. `alias = Athina` is the
     Greek name; `defined_as = The Greek government` is the Greek one. The referent is known, the
     surface does not repeat its marker.
  3. EDGES THAT BELONG TO NO ATHENS AT ALL. `defined_as = The genitalia`, `Located on a higher
     floor or level of a building`, `alias = Up the stairs`. The senses of "upstairs" are merged
     into this node. That is not an unplaced Athens edge -- it is a different word.

Kind 3 is why this module exists rather than a second pass of `attribution`. "I cannot tell which
Athens" and "this is not Athens" call for opposite repairs: the first wants more evidence, the
second wants the edge detached. Collapsing them would send acquisition hunting for an Athens that
the genitalia sense belongs to, forever.

NOTHING IS WRITTEN. This proposes; the split itself is an operator-gated store mutation.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from packages.knowledge_repair.attribution import Referent

Edge = tuple[str, str, str]


@dataclass(frozen=True)
class EdgeVerdict:
    """Where one unplaced edge belongs, or the honest reason it is still unplaced."""
    edge: Edge
    referent: str | None            # set only for "assigned"
    outcome: str                    # "assigned" | "foreign" | "unknown"
    basis: str

    @property
    def placed(self) -> bool:
        return self.outcome == "assigned"


def referents_from_edges(name: str, edges: Iterable[Edge], *,
                         min_len: int = 3) -> list[Referent]:
    """Referents the GRAPH ITSELF states, from definition-like edges that name a distinct place.

    Kind (1). The graph is a source, and for a merged node it is often the RICHEST one: the object
    text of a `defined_as` edge frequently is a disambiguation entry. Extraction is the trailing
    proper-name phrase ("...in Claiborne Parish, Louisiana" -> Louisiana), which is where the
    qualifier sits in this construction -- never invented, only read off the object."""
    tail = re.compile(r"(?:\bin\b|,)\s+(?P<qual>[A-Z][\w'\-\.]*(?:\s+[A-Z][\w'\-\.]*){0,3})\s*$")
    found: dict[str, set[str]] = {}
    for _s, _p, obj in edges:
        m = tail.search(str(obj).strip().rstrip("."))
        if not m:
            continue
        qual = m.group("qual").strip()
        if len(qual) < min_len or qual.lower() == name.lower():
            continue
        found.setdefault(qual, set()).update(
            w for w in re.split(r"[^\w'\-]+", qual) if len(w) > 2)
    return [Referent(f"{name} ({q})", frozenset(m)) for q, m in sorted(found.items())]


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w'\-]+", str(text or "").lower()) if len(t) > 2}


def _bridging(docs: Sequence[set[str]], *, max_share: float = 0.34) -> set[str]:
    """Words that appear across too many separate edges to distinguish anything.

    Not a stop-word list. Cohesion is measured by shared vocabulary, so any word appearing in a
    large fraction of edges links every cluster to every other and the separation collapses --
    measured: `the` occurs in both the "upstairs" definitions and the Greece ones, and its presence
    alone made `floor`/`level` look connected to the place vocabulary.

    A hand list was rejected because the bridging words are corpus-specific: in the real Athens
    residue they include `county` (38 of 135 edges), which is not a stop word at all but is equally
    useless for separating one Athens from another. Which words bridge is a property of the data,
    so it is read from the data."""
    if len(docs) < 3:
        return set()
    counts: Counter = Counter()
    for d in docs:
        counts.update(d)
    ceiling = max(2, int(len(docs) * max_share))
    return {w for w, n in counts.items() if n > ceiling}


def foreign_vocabulary(edges: Sequence[Edge], referents: Sequence[Referent],
                       *, min_share: int = 2) -> frozenset[str]:
    """Vocabulary that COHERES with itself and with none of the referents' own edges.

    Kind (3), detected structurally rather than by naming "upstairs" anywhere.

    Frequency alone was tried first and measured wrong: across the 135 real unplaced Athens edges
    the commonest tokens are `county` 38, `town` 11, `village` 8, `city` 7 -- the vocabulary of the
    GENUINE Athenses -- alongside stop words (`the` 13, `and` 9). A frequency cut keeps the noise
    and discards the signal.

    What actually separates a second lexeme is COHESION: `floor`, `stairs`, `storey`, `level`
    co-occur with each other and never with the place vocabulary. So a word is foreign when it
    recurs AND its company is disjoint from the vocabulary of edges that a referent already claims.
    A single odd definition still fails the recurrence test, which is what keeps noise out.

    ONE CLUSTER PER PASS, measured on the real node and left that way deliberately. Athens turned
    out to carry at least THREE lexemes -- the places, the senses of "upstairs", and the senses of
    "daily" (`every day`, `diurnally`, `a cleaner who comes in daily`, and a dart board). A single
    pass detaches the most cohesive foreign cluster and leaves the rest `unknown`, because once its
    vocabulary is removed the next cluster's cohesion is measured against a cleaner background.
    Chasing all of them at once would require deciding how many lexemes there are, which is exactly
    the guess this module refuses to make. Successive rounds are the intended shape."""
    marker_words = {w.lower() for r in referents for w in r.markers}
    all_docs = [_tokens(o) for _s, _p, o in edges]
    bridge = _bridging(all_docs)                   # read off the data, never listed

    placed_vocab: set[str] = set()
    free: list[set[str]] = []
    for toks in all_docs:
        toks = toks - bridge
        if toks & marker_words:                    # this edge belongs to a known referent
            placed_vocab |= toks
        else:
            free.append(toks)

    counts: Counter = Counter()
    for toks in free:
        counts.update(toks)
    recurring = {w for w, n in counts.items() if n >= min_share}

    # keep only words whose OWN company never touches vocabulary a referent's edges use
    out = set()
    for w in recurring:
        company: set[str] = set()
        for toks in free:
            if w in toks:
                company |= toks
        if not (company & placed_vocab) and not (company & marker_words):
            out.add(w)
    return frozenset(out)


def attribute_edges(name: str, unplaced: Sequence[Edge], referents: Sequence[Referent],
                    *, alias_hints: dict[str, str] | None = None) -> list[EdgeVerdict]:
    """Verdict per unplaced edge: assigned, foreign, or honestly unknown.

    `alias_hints` (kind 2) maps a surface the graph does not connect -- "Athina" -> "Athens
    (Greece)" -- and is supplied by acquisition, never hardcoded here. Absent hints, such edges
    stay `unknown`, which is correct: the module does not know that Athina is Greek."""
    hints = {k.lower(): v for k, v in (alias_hints or {}).items()}
    foreign = foreign_vocabulary(unplaced, referents)
    out: list[EdgeVerdict] = []

    for edge in unplaced:
        _s, _p, obj = edge
        obj_l = str(obj).lower()
        toks = _tokens(obj)

        hit = [r for r in referents
               if any(m.lower() in obj_l for m in r.markers)]
        if len(hit) == 1:
            out.append(EdgeVerdict(edge, hit[0].key, "assigned", "object names this referent"))
            continue

        hinted = next((v for k, v in hints.items() if k in obj_l), None)
        if hinted and not hit:
            out.append(EdgeVerdict(edge, hinted, "assigned", "acquired alias hint"))
            continue

        shared = toks & foreign
        if shared and not hit:
            out.append(EdgeVerdict(
                edge, None, "foreign",
                f"vocabulary of another word sharing this surface: {', '.join(sorted(shared)[:4])}"))
            continue

        out.append(EdgeVerdict(
            edge, None, "unknown",
            "no referent named and no evidence it belongs elsewhere" if not hit
            else "several referents match; evidence does not separate them"))
    return out


def summarise(verdicts: Sequence[EdgeVerdict]) -> dict[str, Any]:
    """Counts plus the questions still worth asking. `foreign` is progress, not residue: those
    edges are resolved -- they simply do not belong to this node."""
    by = Counter(v.outcome for v in verdicts)
    return {
        "assigned": by["assigned"], "foreign": by["foreign"], "unknown": by["unknown"],
        "resolved": by["assigned"] + by["foreign"], "total": len(verdicts),
        "open_questions": [f"Which '{v.edge[0]}' has {v.edge[1]} = '{v.edge[2]}'?"
                           for v in verdicts if v.outcome == "unknown"][:10],
    }
