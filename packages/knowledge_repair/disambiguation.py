# -*- coding: utf-8 -*-
"""A1a — acquire the REFERENTS a merged name stands for. A list, not a value.

Why this is its own capability and not a call into the existing loop (measured 2026-07-28 before
writing any of it): `knowledge_acquisition.loop.acquire()` answers "what is entity E's relation
R?" -- it fills a missing VALUE. Merged-node residue asks the inverse, "which E does this value
belong to?", and its questions do not even parse there:

    "Which 'Athens' has alias = 'Athina'?"                  -> parse_relational_shape: None
    "What are the distinct places named Athens?"            -> None
    "What is the country of Athens?"                        -> parses (the shape it was built for)

A contract match is not a capability match. Forcing residue through that loop would have meant the
adapter this line of work exists to remove.

WHAT IS REUSED: the search + fetch cascade, unchanged (`EvidenceSource.documents` already takes a
free-form query). Only the EXTRACTION is new, because a disambiguation source states a list of
distinct referents, each with the qualifier that separates it -- which is exactly the `Referent`
markers `attribution` consumes.

WHAT IS NOT DONE HERE: deciding which edge belongs to which referent (that is A1b), and writing
anything to a store. This proposes referents; the graph is not touched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from packages.knowledge_repair.attribution import Referent

# A source line that separates one referent from another almost always does it with a PLACE or
# KIND qualifier in parentheses or after a comma: "Athens, Georgia", "Athens (Ohio)", "Mercury
# (planet)". These are the two orthographic conventions disambiguation pages use; the CONTENT of
# the qualifier is never guessed, only extracted.
_PAREN = re.compile(r"^\s*(?P<name>[^(]{2,60}?)\s*\((?P<qual>[^)]{2,60})\)")
# The comma form's qualifier is a PROPER-NAME PHRASE, not the rest of the sentence. Measured:
# an unbounded run captured "Georgia is a consolidated city-county in the United" from
# "Athens, Georgia is a consolidated city-county in the United States." -- a referent key that
# would match almost nothing and pollute the marker set. Capitalised words only, and it stops at
# the first lowercase word, which is where the qualifier ends and the predication begins.
_COMMA = re.compile(
    r"^\s*(?P<name>[A-Z][\w'\-\.]{1,40})\s*,\s*"
    r"(?P<qual>[A-Z][\w'\-\.]*(?:\s+[A-Z][\w'\-\.]*){0,3})(?![\w'\-])")


@dataclass(frozen=True)
class ReferentProposal:
    """One candidate referent, with the sources that stated it. Never promoted here."""
    key: str
    markers: frozenset[str]
    sources: tuple[str, ...]

    @property
    def corroboration(self) -> int:
        return len(set(self.sources))

    def as_referent(self) -> Referent:
        return Referent(self.key, self.markers)


def disambiguation_query(name: str) -> str:
    """The question a disambiguation source answers. Phrased as the OPEN question -- it must not
    presuppose how many referents exist, or the extraction would be fitting a guess."""
    return f"{name} disambiguation distinct places or things named {name}"


def _candidates(name: str, text: str) -> list[tuple[str, str]]:
    """(display, qualifier) pairs a document states for this name."""
    out: list[tuple[str, str]] = []
    low = name.strip().lower()
    for raw in re.split(r"[\n;]+", text or ""):
        line = raw.strip()
        if len(line) < 4 or low not in line.lower():
            continue
        for rx in (_PAREN, _COMMA):
            m = rx.match(line)
            if m and low in m.group("name").strip().lower():
                qual = m.group("qual").strip()
                if qual and qual.lower() != low:
                    out.append((m.group("name").strip(), qual))
                break
    return out


def propose_referents(name: str, documents: Iterable[tuple[str, str]], *,
                      min_corroboration: int = 2) -> list[ReferentProposal]:
    """Referents the SOURCES state for a name, kept only when more than one source says so.

    Corroboration is the same k-source discipline the acquisition loop uses for values, applied to
    identity: one page asserting a referent is a claim, two independent ones are evidence. A wrong
    referent is worse than a missing one -- it would attract edges that then look placed."""
    seen: dict[str, set[str]] = {}
    srcs: dict[str, set[str]] = {}
    for url, text in documents:
        for _display, qual in _candidates(name, text):
            key = f"{name} ({qual})"
            seen.setdefault(key, set()).update(
                w for w in re.split(r"[^\w'\-]+", qual) if len(w) > 2)
            srcs.setdefault(key, set()).add(str(url))

    out = [ReferentProposal(k, frozenset(seen[k]), tuple(sorted(srcs[k])))
           for k in seen if len(srcs[k]) >= min_corroboration]
    out.sort(key=lambda p: (-p.corroboration, p.key))
    return out


def acquire_referents(name: str, evidence: Any, *, min_corroboration: int = 2,
                      log: Any = None) -> list[ReferentProposal]:
    """Search for what a name refers to, and propose only corroborated referents.

    Returns [] on any source failure -- an empty proposal keeps the node merged and honest, which
    is the correct outcome when nothing could be learned. Never raises into the caller."""
    try:
        docs = evidence.documents(name, "disambiguation", disambiguation_query(name)) or []
    except Exception:
        return []
    props = propose_referents(name, docs, min_corroboration=min_corroboration)
    if log:
        try:
            log(name=name, documents=len(docs), proposed=len(props))
        except Exception:
            pass
    return props
