# -*- coding: utf-8 -*-
"""Restore the PRIMARY definitions the old 160-char ingest cap deleted. DRY RUN by default.

WHY (measured 2026-07-17)
 ingest_kaikki._clean_gloss capped glosses at 160 chars — the 96.5th percentile, i.e. inside
 the body of real definitions. And it did not cut randomly: a well-documented word's sense-1
 gloss is its longest, most careful one, so the cap systematically deleted the BEST definition
 and kept the terse minor senses. Over 120k entries it dropped 10,039 glosses (3.5%), of which
 5,320 were a sense-1 gloss — 4.4% of entries lost their primary definition. Observed:

 crocodile lost "Any of the predatory amphibious reptiles of the family Crocodylidae…"
 and answered with sense 2: "A long line or procession of people…"
 encyclopedia lost its ONLY English definition (the store held nothing but ,
 which the language gate then — correctly — refuses to surface)
 word same, and 'word' is not an obscure entry

 The cap is fixed (400, above p99.9). This backfills what the old cap already ate.

WHY A DIFF AND NOT A RE-INGEST
 TripleStore.add() dedupes against `_seen`, which starts EMPTY and is never rebuilt from
 disk — so re-running ingest_kaikki --apply appends a duplicate of every row it already
 wrote (3.5M defined_as). The only safe path is to diff against the store: for each entry,
 add ONLY glosses the store does not already hold for that word.

EVIDENCE-ONLY ()
 Every row added is a verbatim gloss the Kaikki dump asserts for that exact headword. Nothing
 is inferred, nothing is deleted, no existing row changes. This is the doctrine's positive
 case: a row a source DOES assert gets to answer.

USAGE
 python scripts/backfill_kaikki_glosses.py --dump data/graph_scale/kaikki-en.jsonl.gz

Direct ``--apply`` is disabled. The measured additions must be emitted as a
reviewed proposal and compiled into a GraphMutationBatch.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_HANGUL = re.compile(r"[가-힣]")
_WS = re.compile(r"\s+")
OLD_CAP = 160          # what the store was built with
NEW_CAP = 400          # ingest_kaikki._GLOSS_MAX today (measured: p99.9 = 338, >400 is 0.03%)


def _clean(g: str) -> str:
    return _WS.sub(" ", str(g)).strip().rstrip(".。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=str(REPO / "data" / "graph_scale" / "kaikki-en.jsonl.gz"))
    ap.add_argument(
        "--apply",
        action="store_true",
        help="disabled: shipped additions require a signed mutation batch",
    )
    ap.add_argument("--limit", type=int, default=0, help="debug: stop after N lines")
    args = ap.parse_args()
    if args.apply:
        print(
            "REFUSING before dump scan: direct shipped-store append is "
            "disabled; emit a reviewed mutation proposal instead."
        )
        return 2

    from packages.graph_scale.lexicon_lane import _store

    st = _store()
    print(f"store rows before: {len(st)}")

    # Candidate glosses: exactly the band the OLD cap ate and the NEW one keeps.
    # Anything <=160 is already in the store; anything >400 the current rule rejects too.
    words: dict[str, list[str]] = {}
    scanned = 0
    t0 = time.time()
    with gzip.open(args.dump, "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if args.limit and i >= args.limit:
                break
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("lang_code") != "en":
                continue
            w = (e.get("word") or "").strip()
            if not w or _HANGUL.search(w):
                continue
            scanned += 1
            for s in e.get("senses") or []:
                for g in s.get("glosses") or []:
                    cg = _clean(g)
                    if OLD_CAP < len(cg) <= NEW_CAP and not _HANGUL.search(cg):
                        words.setdefault(w, [])
                        if cg not in words[w]:
                            words[w].append(cg)
    print(f"scanned {scanned} en entries in {time.time()-t0:.0f}s")
    print(f"words with a gloss in the ({OLD_CAP},{NEW_CAP}] band: {len(words)}")

    # Diff against the store — the ONLY safe dedupe (see module docstring).
    t0 = time.time()
    todo: list[tuple[str, str]] = []
    for j, (w, gs) in enumerate(words.items()):
        try:
            have = {o for _s, p, o in st.facts_about(w, limit=400) if p == "defined_as"}
        except Exception:
            continue
        for g in gs:
            if g not in have:
                todo.append((w, g))
        if j and j % 20000 == 0:
            print(f"  diffed {j}/{len(words)}  new so far {len(todo)}  {time.time()-t0:.0f}s")
    print(f"\nMISSING from the store: {len(todo)} glosses across "
          f"{len({w for w, _ in todo})} words  ({time.time()-t0:.0f}s)")
    for w, g in todo[:8]:
        print(f"  {w}: {g[:88]}")

    print(
        "\nDRY RUN — nothing written. Serialize reviewed additions as a "
        "GraphMutationBatch proposal."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
