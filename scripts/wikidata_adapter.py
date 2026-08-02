#!/usr/bin/env python3
"""Wikidata durable adapter — structured backbone with TIME qualifiers (-> 4D).

Wikidata (CC0) is a real curated knowledge graph. We do NOT render its triples into
prose (no LLM/paraphrase); we map each structured statement DIRECTLY to our graph:
  subject concept + object concept + a typed relation + a temporal block
  {valid_from, valid_to} taken from the statement's start/end qualifiers.

This is the high-value feed for the 4D temporal layer: functional-slot facts like
"<org> — CEO — <person> (2015–…)" arrive WITH validity intervals, exactly what the
TCV verifier needs and what the old graph was starved of (0.2% had dates).

Scoped fetch only: a small SPARQL query (LIMIT) against the public endpoint with a
descriptive User-Agent. No bulk dump. Output is a report + durable rows; writing to
a store is a separate gated step.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPARQL = "https://query.wikidata.org/sparql"
UA = "ATANOR-research/0.1 (graph ontology seed; contact blueyjkim@gmail.com)"

# Scoped: organizations + their CEO (P169) with start (P580) / end (P582) qualifiers.
QUERY = """
SELECT ?org ?orgLabel ?ceo ?ceoLabel ?start ?end WHERE {
  ?org p:P169 ?st.
  ?st ps:P169 ?ceo.
  OPTIONAL { ?st pq:P580 ?start. }
  OPTIONAL { ?st pq:P582 ?end. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
LIMIT %d
"""


def fetch(limit: int) -> list[dict]:
    url = SPARQL + "?" + urllib.parse.urlencode({"query": QUERY % limit, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("results", {}).get("bindings", [])


def to_durable_facts(bindings: list[dict]) -> list[dict]:
    """Map each statement to a structured durable fact (no prose rendering)."""
    facts = []
    for b in bindings:
        org = b.get("orgLabel", {}).get("value", "")
        ceo = b.get("ceoLabel", {}).get("value", "")
        qid = b.get("org", {}).get("value", "")
        if not org or not ceo:
            continue
        start = b.get("start", {}).get("value")
        end = b.get("end", {}).get("value")
        facts.append({
            "subject": org,
            "relation": "chief_executive_officer",   # typed, functional
            "object": ceo,
            "temporal": {
                "valid_from": start[:10] if start else None,
                "valid_to": end[:10] if end else None,
                "t_confidence": 1.0 if start else 0.3,
                "t_grain": "day" if start else "unknown",
            },
            "provenance": {"source": "wikidata", "entity": qid, "license": "CC0"},
        })
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description="Wikidata structured adapter (scoped, CC0)")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", type=Path, default=None, help="optional: write durable facts jsonl")
    args = ap.parse_args()

    print(f"[WIKIDATA] SPARQL fetch (CC0, scoped LIMIT {args.limit}) — CEOs with time qualifiers...")
    bindings = fetch(args.limit)
    facts = to_durable_facts(bindings)
    with_time = [f for f in facts if f["temporal"]["valid_from"]]
    print(f"[WIKIDATA] statements: {len(bindings)} -> structured facts: {len(facts)} | WITH validity interval: {len(with_time)}")
    print("--- sample functional-slot facts WITH 4D temporal (real, CC0) ---")
    for f in with_time[:6]:
        t = f["temporal"]
        print(f"  {f['subject'][:24]} --{f['relation']}--> {f['object'][:20]}  [{t['valid_from']}..{t['valid_to'] or 'now'}]")
    # functional-slot contradiction readiness: same org with >1 CEO over time = a timeline
    import collections
    slots = collections.Counter(f["subject"] for f in facts)
    multi = [o for o, n in slots.items() if n > 1]
    print(f"\n[WIKIDATA] orgs with multiple CEOs over time (TCV timeline candidates): {len(multi)} e.g. {multi[:3]}")
    print("[WIKIDATA] -> these feed functional-slot non-overlap + supersession (4D) directly, no prose, no LLM.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for f in facts:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        print(f"[WIKIDATA] durable facts written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
