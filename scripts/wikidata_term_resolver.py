#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Targeted Wikidata STRUCTURED lookup for named terms — the proper-noun lane.

Structured data only (the sanctioned wikidata class: labels + P31 statements),
never article text. Precision gates, in the harrisi lesson's shadow:
  * the entity's label/alias must EXACTLY equal the term (case-insensitive) —
    fuzzy hits are how wrong referents get in;
  * P31 (instance of) values become is_a edges with their English label,
    plus the entity's Korean label as an alias when present;
  * no exact match -> the term stays an HONEST gap.

  python scripts/wikidata_term_resolver.py Lusatia KOFAD ... [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.graph_paths import (  # noqa: E402
    WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT,
)

API = "https://www.wikidata.org/w/api.php"
UA = "ATANOR-research/0.1 (graph ontology seed; contact blueyjkim@gmail.com)"


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve(term: str) -> list[tuple[str, str, str]]:
    hits = _get({"action": "wbsearchentities", "search": term, "language": "en",
                 "type": "item", "limit": 5}).get("search", [])
    tl = term.lower()
    exact = [h for h in hits
             if str(h.get("label", "")).lower() == tl
             or any(str(a).lower() == tl for a in (h.get("aliases") or []))]
    if not exact:
        return []
    qid = exact[0]["id"]
    ent = _get({"action": "wbgetentities", "ids": qid,
                "props": "claims|labels"}).get("entities", {}).get(qid, {})
    triples: list[tuple[str, str, str]] = []
    ko_label = (ent.get("labels", {}).get("ko") or {}).get("value")
    if ko_label and ko_label != term:
        triples.append((term, "alias", ko_label))
    p31_qids = []
    for st in (ent.get("claims", {}).get("P31") or [])[:4]:
        try:
            p31_qids.append(st["mainsnak"]["datavalue"]["value"]["id"])
        except Exception:
            continue
    if p31_qids:
        labels = _get({"action": "wbgetentities", "ids": "|".join(p31_qids),
                       "props": "labels"}).get("entities", {})
        for q in p31_qids:
            lab = ((labels.get(q, {}).get("labels", {}).get("en") or {}).get("value"))
            ko = ((labels.get(q, {}).get("labels", {}).get("ko") or {}).get("value"))
            if lab:
                triples.append((term, "is_a", lab))
            if ko and ko != lab:
                triples.append((term, "is_a", ko))
    return triples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    store = None
    if args.apply:
        from packages.graph_scale.triple_store import TripleStore
        store = TripleStore(WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT)
    added = 0
    for term in args.terms:
        try:
            triples = resolve(term)
        except Exception as exc:  # noqa: BLE001
            print(f"  {term}: lookup failed ({exc})")
            continue
        if not triples:
            print(f"  {term}: no EXACT wikidata entity (honest gap)")
            continue
        for s, p, o in triples:
            print(f"  {s} | {p} | {o}")
            if store is not None and store.add(s, p, o):
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
