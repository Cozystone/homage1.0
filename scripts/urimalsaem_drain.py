#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" API lane — the National Institute of Korean Language's dictionary.

The lane the whole abstain analysis pointed at: the common Sino-Korean noun
class (///…) exists NOWHERE else as free definitions (ko wiktionary
= no-gloss stubs, measured). This is curated lexicographic data, same source
class as kaikki/ConceptNet — definitions ingested verbatim as defined_as,
exact-headword gate, first senses only, source cited.

 python scripts/urimalsaem_drain.py ... [--apply]
Key: URIMALSAEM_API_KEY env or .env line.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.graph_paths import (  # noqa: E402
    URIMALSEM_PROPOSAL_FRAGMENT_ROOT,
)

API = "https://opendict.korean.go.kr/api/search"


def _key() -> str:
    k = os.environ.get("URIMALSAEM_API_KEY", "").strip()
    if not k:
        env = REPO / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("URIMALSAEM_API_KEY="):
                    k = line.split("=", 1)[1].strip()
    if not k:
        raise SystemExit("URIMALSAEM_API_KEY missing")
    return k


def _clean(d: str) -> str | None:
    d = re.sub(r"\s+", " ", d).strip().rstrip(".。")
    return d if 4 <= len(d) <= 200 else None


def definitions(term: str, key: str, limit: int = 3) -> list[str]:
    params = {"key": key, "q": term, "req_type": "json", "part": "word",
              "sort": "dict", "start": 1, "num": 10, "advanced": "y",
              "method": "exact"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ATANOR/1.0 (blueyjkim@gmail.com)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        payload = json.loads(r.read().decode("utf-8"))
    out: list[str] = []
    for item in (payload.get("channel", {}).get("item") or []):
        word = re.sub(r"[\^\-0-9]", "", str(item.get("word") or ""))
        if word != term:  # exact headword only — no fuzzy referents
            continue
        senses = item.get("sense")
        if isinstance(senses, dict):
            senses = [senses]
        for s in senses or []:
            d = _clean(str(s.get("definition") or ""))
            if d and d not in out:
                out.append(d)
            if len(out) >= limit:
                return out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    key = _key()
    store = None
    if args.apply:
        from packages.graph_scale.triple_store import TripleStore
        store = TripleStore(URIMALSEM_PROPOSAL_FRAGMENT_ROOT)
    added = 0
    for term in args.terms:
        try:
            defs = definitions(term, key)
        except Exception as exc:  # noqa: BLE001
            print(f"  {term}: API error ({exc})")
            continue
        if not defs:
            print(f"  {term}: no exact entry (honest gap)")
            continue
        for d in defs:
            print(f"  {term} | defined_as | {d[:70]}")
            if store is not None and store.add(term, "defined_as", d):
                added += 1
    if store is not None:
        store.flush()
        print(
            f"wrote {added} unsealed proposal-fragment rows; "
            f"fragment now {len(store)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
