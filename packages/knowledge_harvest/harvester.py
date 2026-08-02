# -*- coding: utf-8 -*-
"""Bounded relational-fact harvester: Wikidata SPARQL (preferred) + curated CSV (fallback).

Every produced edge is a dict ``{"subject", "relation", "object", "source"}`` where ``source`` is
``"wikidata"`` (pulled live from query.wikidata.org, verbatim) or ``"curated"`` (a bundled,
human-checked CSV row). NOTHING is invented: the harvester only transcribes what the structured
source states. The relation names are the SAME snake_case predicate labels the base_brain
relational lane resolves against (``relational_lookup.REL_SYNONYMS``): capital, population,
currency, official_language, located_in, author, inventor.

Network is optional. ``harvest()`` prefers the live Wikidata pull; if the network is unreachable
(or ``prefer_live=False``) it falls back to the curated CSV and SAYS which path ran in the report.
Rate-limited, honest User-Agent (per WDQS etiquette). Deterministic offline path for tests.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_HERE = Path(__file__).resolve().parent
CURATED_CSV = _HERE / "curated_facts.csv"

# WDQS endpoint + etiquette. A scoped query answers fast; a broad "?s wdt:P31 ?o" scan times out.
_WD_SPARQL = "https://query.wikidata.org/sparql"
_UA = "ATANOR-KG/1.0 (local-first No-LLM knowledge engine; contact: local operator)"

# our snake_case relation label  ->  Wikidata property id (documentation of the mapping)
RELATION_PIDS: dict[str, str] = {
    "capital": "P36",
    "population": "P1082",
    "currency": "P38",
    "official_language": "P37",
    "located_in": "P30",          # P30 = continent (country -> continent)
    "author": "P50",
    "inventor": "P61",            # P61 = discoverer or inventor
}

# Countries + their capital / population / currency / official language / continent, in ONE scoped
# query. wdt: is the TRUTHY (preferred-rank) value, so population returns one number, not every
# historical census. LIMIT bounds it; ~200 sovereign states exist.
_WD_COUNTRIES = """
SELECT ?countryLabel ?capitalLabel ?population ?currencyLabel ?langLabel ?continentLabel WHERE {
  ?country wdt:P31 wd:Q6256 .
  OPTIONAL { ?country wdt:P36 ?capital . }
  OPTIONAL { ?country wdt:P1082 ?population . }
  OPTIONAL { ?country wdt:P38 ?currency . }
  OPTIONAL { ?country wdt:P37 ?lang . }
  OPTIONAL { ?country wdt:P30 ?continent . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT %d
"""

# Major written works + their author, ranked by sitelink count so only WELL-KNOWN works are pulled
# (Hamlet, Romeo and Juliet, …). Q7725634 literary work, Q25379 play, Q571 book, Q49084 short story,
# Q1985406 verse novel, Q5185279 poem.
_WD_WORKS = """
SELECT ?workLabel ?authorLabel ?sl WHERE {
  ?work wdt:P50 ?author .
  ?work wikibase:sitelinks ?sl .
  FILTER(?sl >= 55) .
  ?work wdt:P31 ?type .
  FILTER(?type IN (wd:Q7725634, wd:Q25379, wd:Q571, wd:Q49084, wd:Q1985406, wd:Q5185279)) .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
ORDER BY DESC(?sl)
LIMIT %d
"""


@dataclass
class HarvestReport:
    path: str = "none"                       # "wikidata+curated" | "curated_fallback" | "curated_only"
    network_ok: bool = False
    wikidata_edges: int = 0
    curated_edges: int = 0
    wikidata_error: str = ""
    relations: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "network_ok": self.network_ok,
            "wikidata_edges": self.wikidata_edges, "curated_edges": self.curated_edges,
            "wikidata_error": self.wikidata_error, "relations": dict(self.relations),
            "total_edges": self.wikidata_edges + self.curated_edges,
        }


def _humanize_population(raw: str) -> str:
    """A population number the way a person would say it. Wikidata's exact integer is honest but
    'The population of Japan is 123653000' reads poorly; '123.7 million' preserves the figure and
    the fact that population is an approximate, time-varying quantity."""
    try:
        n = int(float(str(raw).replace(",", "").strip()))
    except Exception:
        return str(raw).strip()
    if n <= 0:
        return str(raw).strip()
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f} billion"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} million"
    if n >= 1_000:
        return f"{n:,}"
    return str(n)


def _sparql(query: str, timeout: float) -> list[dict[str, Any]]:
    url = _WD_SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("results", {}).get("bindings", [])


def _val(binding: dict[str, Any], key: str) -> str:
    return str(binding.get(key, {}).get("value", "")).strip()


def _is_qid(s: str) -> bool:
    return len(s) >= 2 and s[0] == "Q" and s[1:].isdigit()


def fetch_wikidata_countries(limit: int = 300, timeout: float = 45.0) -> list[dict[str, str]]:
    """capital / population / currency / official_language / located_in edges for countries."""
    rows = _sparql(_WD_COUNTRIES % int(limit), timeout)
    # a country may bind several currencies/languages across OPTIONALs -> keep first per (subj, rel)
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []
    for b in rows:
        country = _val(b, "countryLabel")
        if not country or _is_qid(country):
            continue
        pairs = [
            ("capital", _val(b, "capitalLabel")),
            ("population", _humanize_population(_val(b, "population")) if _val(b, "population") else ""),
            ("currency", _val(b, "currencyLabel")),
            ("official_language", _val(b, "langLabel")),
            ("located_in", _val(b, "continentLabel")),
        ]
        for rel, obj in pairs:
            if not obj or _is_qid(obj):
                continue
            k = (country, rel)
            if k in seen:
                continue
            seen.add(k)
            edges.append({"subject": country, "relation": rel, "object": obj, "source": "wikidata"})
    return edges


def fetch_wikidata_works(limit: int = 250, timeout: float = 45.0) -> list[dict[str, str]]:
    """author edges for well-known written works (work --author--> person)."""
    rows = _sparql(_WD_WORKS % int(limit), timeout)
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []
    for b in rows:
        work = _val(b, "workLabel")
        author = _val(b, "authorLabel")
        if not work or not author or _is_qid(work) or _is_qid(author):
            continue
        k = (work, "author")
        if k in seen:
            continue
        seen.add(k)
        edges.append({"subject": work, "relation": "author", "object": author, "source": "wikidata"})
    return edges


def load_curated(path: Path | str = CURATED_CSV) -> list[dict[str, str]]:
    """Bundled human-checked relational facts: subject,relation,object (header row required)."""
    p = Path(path)
    out: list[dict[str, str]] = []
    if not p.exists():
        return out
    with p.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            s = str(row.get("subject", "")).strip()
            rel = str(row.get("relation", "")).strip()
            o = str(row.get("object", "")).strip()
            if s and rel and o and not s.startswith("#"):
                out.append({"subject": s, "relation": rel, "object": o, "source": "curated"})
    return out


def _dedupe_keep_first(edges: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """First writer of a (subject, relation) wins — so a live Wikidata value is not overwritten by a
    curated one for the same slot, and vice-versa when curated leads."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for e in edges:
        k = (e["subject"].lower(), e["relation"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def harvest(prefer_live: bool = True, timeout: float = 45.0,
            countries_limit: int = 300, works_limit: int = 250,
            inter_query_delay: float = 2.0,
            curated_path: Path | str = CURATED_CSV) -> tuple[list[dict[str, str]], HarvestReport]:
    """Return (edges, report). Wikidata-first; the curated CSV SUPPLEMENTS slots the live pull did
    not cover, and is the sole source if the network is unreachable. Never raises on a network
    failure — it degrades to the curated fallback and records the error in the report.

    Each SPARQL query has its OWN try/except so a PARTIAL live pull is kept (WDQS was observed rate-
    limiting to 1 req/min during an outage — the countries pull can succeed while the works pull is
    throttled; the country edges must not be discarded). ``inter_query_delay`` spaces the two queries
    (raise it toward 65s when WDQS is throttling to 1 req/min)."""
    report = HarvestReport()
    live: list[dict[str, str]] = []
    errors: list[str] = []
    if prefer_live:
        for name, fetch, lim in (("countries", fetch_wikidata_countries, countries_limit),
                                 ("works", fetch_wikidata_works, works_limit)):
            try:
                live += fetch(lim, timeout)
            except Exception as exc:                         # network/HTTP/parse — keep going
                errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
            time.sleep(inter_query_delay)                    # WDQS etiquette between queries
        report.network_ok = bool(live)
        report.wikidata_error = "; ".join(errors)

    curated = load_curated(curated_path)

    if live:
        # live leads; curated fills only (subject, relation) slots live did not provide
        merged = _dedupe_keep_first(list(live) + curated)
        report.path = "wikidata+curated"
    else:
        merged = _dedupe_keep_first(curated)
        report.path = "curated_fallback" if prefer_live else "curated_only"

    report.wikidata_edges = sum(1 for e in merged if e["source"] == "wikidata")
    report.curated_edges = sum(1 for e in merged if e["source"] == "curated")
    for e in merged:
        report.relations[e["relation"]] = report.relations.get(e["relation"], 0) + 1
    return merged, report
