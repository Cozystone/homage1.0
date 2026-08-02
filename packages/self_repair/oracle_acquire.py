# -*- coding: utf-8 -*-
"""Acquire the evidence the arbiter lacks — from the live web, under consensus, without circularity.

    from packages.self_repair.oracle_acquire import acquire_for
    acquire_for("kiosk", "capable_of", excluding_cue="intended to")

WHY THIS IS THE LAST GAP. The loop measured its own constraint honestly and then hit one that
enumeration could not fix: 115M triples know 97% of the disputed subjects and hold THREE capable_of
facts about them. Not a wiring problem this time — the facts are genuinely absent from every corpus on
disk. But absent from OUR CORPORA is not absent from the world, and the machinery to go and get them
already exists and was deliberately switched off for the sealed runs: WebEvidence, a 2-distinct-domain
consensus gate, SearXNG live on :8888.

THE CIRCULARITY THIS HAS TO AVOID, because it is not obvious and it would invalidate everything. The
dispute is "does the cue `intended to` mean capable_of". If we fetch web pages and mine them with the
SAME extractor, that extractor applies the same disputed mapping to every page, and 2-domain consensus
then confirms a systematic error rather than a fact. Consensus across domains checks whether a FACT is
reliably reported; it cannot check whether our RELATION assignment is right, and the second is exactly
what is in dispute.

So the disputed cue is EXCLUDED from the extractor while acquiring. Only patterns already trusted are
used, so what comes back is independent knowledge about the subject — "a kiosk can dispense tickets"
learned from cues that were never in question — and the disputed proposal is then judged against it.
Evidence that could only have been produced by the claim under test is not evidence.

WHAT IS WRITTEN AND WHERE. Acquired facts land in their own file, tagged `acquired:web` with the URLs
and domains that corroborated them. They never merge silently into the curated sources, and
`oracle_sources.OURS` keeps anything our own pipelines produced out of the arbiter — so an acquired
fact is auditable back to the pages that supported it, and can be dropped wholesale if the acquisition
is ever found wanting.

RATE AND POLITENESS are the existing fetcher's business, not re-implemented here. This asks for one
subject at a time and stops when the caller stops.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ACQUIRED = REPO / "data" / "self_repair" / "acquired_oracle.jsonl"


def _trusted_patterns(excluding_cue: str | None):
    """The extractor's patterns MINUS the one under dispute.

    A cue is identified by its literal words appearing in the pattern source, which is crude and is
    checked by the caller's own eyes in the returned `excluded` list rather than trusted silently."""
    from packages.graph_scale.property_extraction import PATTERNS
    if not excluding_cue:
        return list(PATTERNS), []
    words = [w for w in str(excluding_cue).split() if w]
    kept, dropped = [], []
    for pred, rx in PATTERNS:
        src = rx.pattern.lower()
        if all(re_escape_in(w, src) for w in words):
            dropped.append((pred, rx.pattern[:60]))
        else:
            kept.append((pred, rx))
    return kept, dropped


def re_escape_in(word: str, pattern_src: str) -> bool:
    """Does this literal word appear in the pattern source, escaped or plain?"""
    return word.lower() in pattern_src or ("\\ ".join(word.lower())) in pattern_src


def acquire_for(subject: str, relation: str, *, excluding_cue: str | None = None,
                min_domains: int = 2, budget_docs: int = 8) -> dict:
    """Fetch, mine with trusted cues only, and keep what two distinct domains agree on."""
    from packages.knowledge_acquisition.consensus import ConsensusTally
    from packages.knowledge_acquisition.evidence import WebEvidence

    kept, dropped = _trusted_patterns(excluding_cue)
    if excluding_cue and not dropped:
        return {"subject": subject, "relation": relation, "acquired": [],
                "error": (f"the cue {excluding_cue!r} was not found in the extractor's patterns, so "
                          f"it could not be excluded. Refusing to acquire with a possibly-circular "
                          f"extractor")}

    try:
        docs = WebEvidence(count=budget_docs).documents(subject, relation.replace("_", " "))
    except Exception as exc:
        return {"subject": subject, "relation": relation, "acquired": [],
                "error": f"web evidence unavailable: {type(exc).__name__}: {exc}"}

    tally = ConsensusTally(min_domains=min_domains)
    sightings = 0
    for url, text in docs:
        for _pred, rx in kept:
            if _pred != relation:
                continue
            for m in rx.finditer(text):
                from packages.graph_scale.property_extraction import clean_object
                o = clean_object(m.group(1))
                if o:
                    tally.add(o, url)
                    sightings += 1

    # `_ranked()` returns (object, N_DOMAINS) -- an integer, not a set. The first version called
    # len() on that integer, the TypeError was swallowed by a bare `except Exception: pass`, and the
    # result was ZERO corroborated facts on every run. I nearly reported that as "the consensus gate
    # correctly refused". A defensive catch that hides a type error is not defensive.
    ranked = tally._ranked()
    corroborated = [{"object": obj, "domains": int(n)}
                    for obj, n in ranked if int(n) >= min_domains]
    below_floor = [{"object": obj, "domains": int(n)}
                   for obj, n in ranked if int(n) < min_domains][:8]

    rec = {
        "subject": subject, "relation": relation, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "excluded_cue": excluding_cue,
        "excluded_patterns": [p for _pred, p in dropped],
        "documents": len(docs), "sightings": sightings,
        "acquired": corroborated,
        "below_consensus_floor": below_floor,
        "min_domains": min_domains,
        "note": ("mined with the disputed cue EXCLUDED, so what came back is independent of the "
                 "claim under test"),
    }
    if corroborated:
        ACQUIRED.parent.mkdir(parents=True, exist_ok=True)
        with ACQUIRED.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def acquired_oracle() -> dict:
    """Everything acquired so far, in the arbiter's shape: subject -> ["Relation:object", ...]."""
    out: dict = {}
    if not ACQUIRED.exists():
        return out
    for line in ACQUIRED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ext = "".join(p.capitalize() for p in str(r.get("relation", "")).split("_"))
        for a in r.get("acquired") or []:
            out.setdefault(str(r.get("subject", "")).lower(), []).append(f"{ext}:{a['object']}")
    return out
