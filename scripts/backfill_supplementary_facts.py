# -*- coding: utf-8 -*-
"""C2 part B (owner-directed , read-only overlay path): the world-pack build stopped early and
MISSES major-entity facts entirely (measured 2026-07-18: // have NO capital
relation, no country). A label backfill can't add a fact that isn't there. This fetches those
missing high-value facts from Wikidata (SPARQL, verified source) into a READ-ONLY overlay
`data/graph_scale/supplementary_facts.jsonl` — NOT the triple store ( respected: every
row carries its Wikidata source; delete the file and the overlay is gone, the graph unchanged).

Broad by construction (ALL sovereign states' capitals, both directions, en+ko keys) so it fixes the
pillar, not just the canonical-20 audit (no Goodhart). Run: python scripts/backfill_supplementary_facts.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "graph_scale" / "supplementary_facts.jsonl"
_UA = "ATANOR-C2-supplementary-facts/1.0 (research; blueyjkim@gmail.com)"
_EP = "https://query.wikidata.org/sparql"

# (relation, SPARQL, reverse_relation|None): each row binds ?s/?o with en+ko labels. Verified,
# sourced facts only. Bounded to MAJOR entities (sovereign states, high-sitelink cities/people) so
# the overlay covers the pillar's core without an unbounded fetch.
_LAB = ("?s rdfs:label ?sLabel FILTER(lang(?sLabel)='en'). OPTIONAL{?s rdfs:label ?sLabelKo FILTER(lang(?sLabelKo)='ko')} "
        "?o rdfs:label ?oLabel FILTER(lang(?oLabel)='en'). OPTIONAL{?o rdfs:label ?oLabelKo FILTER(lang(?oLabelKo)='ko')}")
QUERIES = {
    # (SPARQL, reverse-relation): sovereign states → capital (+ capital→country reverse)
    "capital": ("SELECT ?sLabel ?sLabelKo ?oLabel ?oLabelKo WHERE { ?s wdt:P31 wd:Q3624078 . ?s wdt:P36 ?o . " + _LAB + " }",
                "country"),
    # country → continent (P30)
    "continent": ("SELECT ?sLabel ?sLabelKo ?oLabel ?oLabelKo WHERE { ?s wdt:P31 wd:Q3624078 . ?s wdt:P30 ?o . " + _LAB + " }",
                  None),
    # top-sitelink cities → their country (P17), bounded
    "located_country": ("SELECT ?sLabel ?sLabelKo ?oLabel ?oLabelKo WHERE { ?s wdt:P31 wd:Q515 ; wdt:P17 ?o ; wikibase:sitelinks ?sl . "
                        "FILTER(?sl>80) " + _LAB + " } LIMIT 1500", None),
    # most-notable humans → occupation (P106), bounded by sitelinks
    "occupation": ("SELECT ?sLabel ?sLabelKo ?oLabel ?oLabelKo WHERE { ?s wdt:P31 wd:Q5 ; wdt:P106 ?o ; wikibase:sitelinks ?sl . "
                   "FILTER(?sl>120) " + _LAB + " } LIMIT 3000", None),
}


def _sparql(q: str) -> list[dict]:
    url = _EP + "?format=json&query=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "application/sparql-results+json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return d["results"]["bindings"]


def _v(row, k):
    return (row.get(k) or {}).get("value")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows_out: list[dict] = []
    for rel, (q, rev) in QUERIES.items():
        for _try in range(3):
            try:
                rows = _sparql(q)
                break
            except Exception as exc:
                print(f"  {rel} SPARQL error {type(exc).__name__}; retry in 5s", flush=True)
                time.sleep(5)
        else:
            print(f"  {rel}: gave up")
            continue
        print(f"  {rel}: {len(rows)} rows", flush=True)
        for r in rows:
            s_en, s_ko = _v(r, "sLabel"), _v(r, "sLabelKo")
            o_en, o_ko = _v(r, "oLabel"), _v(r, "oLabelKo")
            if not (s_en and o_en):
                continue
            obj = [x for x in (o_en, o_ko) if x]
            for subj in {s_en, s_ko} - {None}:                # key by BOTH en and ko subject labels
                rows_out.append({"subject": subj, "relation": rel, "object": obj, "source": f"wikidata:{rel}"})
            if rev:                                           # reverse direction (capital→country)
                cty = [x for x in (s_en, s_ko) if x]
                for subj in {o_en, o_ko} - {None}:
                    rows_out.append({"subject": subj, "relation": rev, "object": cty,
                                     "source": f"wikidata:{rel}^-1"})
    # de-dup identical rows, write
    seen, uniq = set(), []
    for r in rows_out:
        key = (r["subject"], r["relation"], tuple(r["object"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    with OUT.open("w", encoding="utf-8") as f:
        for r in uniq:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(uniq)} supplementary facts → {OUT.name} (read-only overlay, no store write)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
