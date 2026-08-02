# -*- coding: utf-8 -*-
"""Dominant-sense DEFINITIONS as a READ-ONLY sidecar (: verbatim Kaikki glosses, store
untouched, delete the file to revert). The store holds MANY glosses per word (coffee: 11) but the
answer path surfaces the wrong sense — 'coffee'→coffee-table, 'crocodile'→a fallacious dilemma,
'water'→major constituent of body. The fix is not more glosses, it is SELECTION.

Kaikki/Wiktionary orders a word's senses by dominance: sense-1 is the primary, everyday meaning.
This captures, per English headword, that PRIMARY gloss (first sense, first gloss) — cleaned,
English, of a sane definitional length — so the def path can prefer the dominant sense over the
obscure ones already in the store. Nothing inferred, nothing written to the graph.

Run: python scripts/build_primary_gloss_sidecar.py --dump data/graph_scale/kaikki-en.jsonl.gz
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
OUT = REPO / "data" / "graph_scale" / "primary_gloss.jsonl"
_HANGUL = re.compile(r"[가-힣]")
_WS = re.compile(r"\s+")
# senses whose gloss is really a form-of / inflection / alt-spelling pointer, not a definition
_FORMOF = re.compile(r"^(plural|singular|past tense|present participle|past participle|third-person|"
                     r"alternative (form|spelling)|abbreviation|initialism|acronym|misspelling|"
                     r"obsolete (form|spelling)|synonym of|inflection of|gerund|"
                     r"senses relating to|used (to|in|as|for)|(a )?(surname|male given name|"
                     r"female given name|given name|placename|place name)( |\.|,|:|$)) ?", re.IGNORECASE)


def _clean(g: str) -> str:
    # strip trailing punctuation incl. the ':' Kaikki uses to head a sub-sense list ('…Canidae:')
    return _WS.sub(" ", str(g)).strip().rstrip(".。:;, ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=str(REPO / "data" / "graph_scale" / "kaikki-en.jsonl.gz"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    primary: dict[str, str] = {}
    scanned = kept = 0
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
            if not w or _HANGUL.search(w) or w in primary:   # FIRST entry for the word wins (primary POS)
                continue
            scanned += 1
            # walk senses in order; take the first gloss that is a real definition
            chosen = ""
            for s in e.get("senses") or []:
                for g in s.get("glosses") or []:
                    cg = _clean(g)
                    if (8 <= len(cg) <= 400 and not _HANGUL.search(cg)
                            and not _FORMOF.match(cg)):
                        chosen = cg
                        break
                if chosen:
                    break
            if chosen:
                primary[w] = chosen
                kept += 1
    print(f"scanned {scanned} en headwords, kept {kept} primary glosses in {time.time()-t0:.0f}s")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for w, g in primary.items():
            f.write(json.dumps({"word": w, "gloss": g}, ensure_ascii=False) + "\n")
    print(f"wrote {len(primary)} → {OUT.name} (read-only sidecar, no store write)")
    for w in ("coffee", "water", "sun", "dog", "crocodile", "encyclopedia", "gravity"):
        print(f"  {w}: {primary.get(w, '(none)')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
