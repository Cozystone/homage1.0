# -*- coding: utf-8 -*-
"""Korean clean taxonomy from Wikidata — the source ConceptNet-ko couldn't be.

Diagnosis (2026-07-09): ConceptNet has only ~430 Korean IsA edges — far too sparse
for Korean geometry. Wikidata is the answer: its P279 (subclass_of) / P31
(instance_of) with Korean labels IS a clean, broad Korean taxonomy (→,
→). We pull it live from the Wikidata Query Service (fast, no 100GB dump),
diverse across several relations, into the SAME gated candidate ledgers as every
other clean source. Candidate-tier, never production.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

LEDGER_DIR = Path(__file__).resolve().parents[2] / "data" / "cloud_brain" / "derived_candidates"
_ENDPOINT = "https://query.wikidata.org/sparql"

# Wikidata property -> our predicate. A diverse, CLEAN taxonomy/relation set.
_RELATIONS = {
    "P279": "is_a",       # subclass of
    "P31": "is_a",        # instance of
    "P361": "part_of",    # part of
    "P17": "국가",         # country
    "P131": "소재지",       # located in admin territory
    "P279_super": None,   # (placeholder, unused)
}
_DIVERSE = ("P279", "P31", "P361", "P17", "P131")


def _sparql(query: str, *, timeout: int = 70, retries: int = 4) -> list[dict[str, Any]]:
    """WDQS enforces ~1 req/min under load and 60s query timeout. Respect both:
    small batches, long backoff on 429/timeout."""
    import urllib.error
    url = _ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ATANOR-KG/1.0 (research; graph learning)",
                "Accept": "application/sparql-results+json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))["results"]["bindings"]
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(90.0 if e.code == 429 else 20.0)   # 429 -> wait out the minute
        except Exception as e:
            last = e
            time.sleep(15.0)
    if last:
        raise last
    return []


def _query_for(prop: str, limit: int, offset: int) -> str:
    # NOTE (2026-07-09): blind OFFSET pagination degrades on WDQS — deep offsets
    # (>~6000) exceed the 60s query timeout and, during a WDQS outage, trip the
    # aggressive "1 req/min" 429. So this reliably yields only ~5-6k edges/rel. For
    # more, shard by object (query subclasses under specific parent QIDs) so every
    # query stays shallow (offset 0). Korean Wikipedia categories (wikipedia_ko_
    # categories) are the scalable, un-throttled volume source; Wikidata here is the
    # high-precision complement.
    return (f'SELECT ?iLabel ?sLabel WHERE {{ ?i wdt:{prop} ?s . '
            f'?i rdfs:label ?iLabel . FILTER(lang(?iLabel)="ko") '
            f'?s rdfs:label ?sLabel . FILTER(lang(?sLabel)="ko") }} '
            f'LIMIT {limit} OFFSET {offset}')


def harvest_ko(*, relations: tuple[str, ...] = _DIVERSE, batch: int = 2000,
               max_per_rel: int = 200000, pace_sec: float = 62.0,
               out_dir: str | Path | None = None, log: Any = print) -> dict[str, Any]:
    """Paginate Korean (subject-label, object-label) pairs for each relation and
    append to the candidate ledger. Deduped, candidate-tier, never production."""
    out_dir = Path(out_dir) if out_dir else LEDGER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    totals: dict[str, int] = {}
    for prop in relations:
        pred = _RELATIONS.get(prop) or "related_to"
        path = out_dir / f"wikidata_ko_{pred}.jsonl"
        seen: set[tuple[str, str]] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    seen.add((r.get("s"), r.get("o")))
                except Exception:
                    pass
        written = 0
        offset = 0
        with path.open("a", encoding="utf-8") as fh:
            while offset < max_per_rel:
                try:
                    rows = _sparql(_query_for(prop, batch, offset))
                except Exception as e:
                    log(f"  {prop} offset {offset}: {type(e).__name__} - stopping this rel")
                    break
                if not rows:
                    break
                for b in rows:
                    s = b.get("iLabel", {}).get("value", "").strip()
                    o = b.get("sLabel", {}).get("value", "").strip()
                    if not s or not o or s == o or len(s) > 40 or len(o) > 40:
                        continue
                    if (s, o) in seen:
                        continue
                    seen.add((s, o))
                    fh.write(json.dumps({"s": s, "p": pred, "o": o, "src": "wikidata:ko",
                                         "tier": "candidate", "at": now}, ensure_ascii=False) + "\n")
                    written += 1
                offset += batch
                log(f"  {prop}->{pred}: +{len(rows)} rows (offset {offset}, written {written})")
                if len(rows) < batch:
                    break
                time.sleep(pace_sec)   # respect WDQS ~1 req/min under load
        totals[f"{prop}:{pred}"] = written
    return {"harvested": True, "by_relation": totals,
            "total_written": sum(totals.values()), "written_to_production": False,
            "note": "clean Korean taxonomy from Wikidata Query Service — gated candidates"}
