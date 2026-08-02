#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest a kaikki.org wiktextract dump (curated, structured dictionary data)
into the TripleStore — the defined_as/is_a/alias lanes the abstain analysis
says we're missing.

Same source class as the ConceptNet bulk load: a STRUCTURED curated dump
(wiktextract JSONL), not a per-query web crutch. Conservative by construction:

  defined_as   every sense gloss that is real prose in the dump's language
  is_a         only STRUCTURED hypernym entries (never parsed from text here)
  alias        only single-word same-script synonyms

  python scripts/ingest_kaikki.py <dump.jsonl.gz> --lang ko [--apply]

!! --apply IS NOT IDEMPOTENT. Re-running it on a dump this store already holds appends a
   DUPLICATE of every row. TripleStore.add() dedupes only against what the current process
   added (`_seen` starts empty; nothing rebuilds it from disk), so it cannot see the 3.5M
   defined_as rows already on disk. To widen an extraction rule on an ingested dump, diff
   against the store instead: scripts/backfill_kaikki_glosses.py.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.triple_store import TripleStore  # noqa: E402
from packages.graph_scale.graph_paths import (  # noqa: E402
    KAIKKI_PROPOSAL_FRAGMENT_ROOT,
)

_HANGUL = re.compile(r"[가-힣]")
_WORDISH = re.compile(r"^[가-힣A-Za-z0-9·\- ]{1,40}$")


# MEASURED 2026-07-17 over 120k kaikki-en entries (283,570 glosses):
#     p50 46 | p95 145 | p96.5 161 | p99 220 | p99.9 338 | max 722 | >400 chars: 0.03%
# The old ceiling of 160 sat at the 96.5th percentile — i.e. inside the body of real definitions,
# not out past the junk. And it did not cut randomly: a well-documented word's PRIMARY sense is
# its longest, most careful gloss, so the cap systematically deleted the best definition and kept
# the terse minor senses. It dropped 10,039 glosses (3.5%), of which 5,320 were a sense-1 gloss —
# 4.4% of all entries lost their primary definition. Observed damage:
#     crocodile    lost "Any of the predatory amphibious reptiles of the family Crocodylidae…"
#                  and answered with sense 2: "A long line or procession of people…"

#     word         same, and 'word' is not an obscure entry
# 400 keeps 99.97% of real glosses while still rejecting a runaway extraction artifact. Length is
# a sanity bound here, never a quality signal.
_GLOSS_MAX = 400


def _clean_gloss(g: str) -> str | None:
    g = re.sub(r"\s+", " ", g).strip().rstrip(".。")
    if not (4 <= len(g) <= _GLOSS_MAX):
        return None
    return g


def iter_triples(path: Path, lang: str):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("lang_code") != lang:
                continue
            word = (e.get("word") or "").strip()
            if not word or not _WORDISH.match(word) or len(word) > 30:
                continue
            if lang == "ko" and not _HANGUL.search(word):
                continue
            for sense in e.get("senses") or []:
                for g in sense.get("glosses") or []:
                    cg = _clean_gloss(str(g))
                    if cg and (lang != "ko" or _HANGUL.search(cg)):
                        yield (word, "defined_as", cg)
                # structured hypernyms are the dump ASSERTING is_a — take verbatim
                for h in sense.get("hypernyms") or []:
                    hw = (h.get("word") or "").strip()
                    if hw and _WORDISH.match(hw) and hw != word:
                        yield (word, "is_a", hw)
                for syn in sense.get("synonyms") or []:
                    sw = (syn.get("word") or "").strip()
                    if sw and sw != word and " " not in sw and _WORDISH.match(sw):
                        yield (word, "alias", sw)
            for h in e.get("hypernyms") or []:
                hw = (h.get("word") or "").strip()
                if hw and _WORDISH.match(hw) and hw != word:
                    yield (word, "is_a", hw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    counts = {"defined_as": 0, "is_a": 0, "alias": 0}
    samples: list[tuple[str, str, str]] = []
    store = (
        TripleStore(KAIKKI_PROPOSAL_FRAGMENT_ROOT)
        if args.apply
        else None
    )
    added = 0
    for n, (s, p, o) in enumerate(iter_triples(Path(args.dump), args.lang)):
        counts[p] += 1
        if len(samples) < 10:
            samples.append((s, p, o))
        if store is not None and store.add(s, p, o):
            added += 1
        if args.limit and n >= args.limit:
            break
    print("extracted:", counts)
    for s, p, o in samples:
        print(f"  {s} | {p} | {o[:60]}")
    if store is not None:
        store.flush()
        print(
            f"wrote {added} unsealed proposal-fragment rows; "
            f"fragment now {len(store)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
