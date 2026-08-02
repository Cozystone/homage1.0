# -*- coding: utf-8 -*-
"""Temporal KG v0 — the owner's TRUE 4D: the ontology graph gains a TIME AXIS.

'5 ' ' ' are different FACTS that must be
structurally distinguishable — not one overwritten value. The mechanism is the
4D-fluents pattern (temporal-part modeling: a time-varying property holds only
within a validity slice). Reference framing: TechRxiv 10.36227/
techrxiv.174494561.19053524 (owner-provided; 4D = 3D ontology + time axis).

v0 representation (auditable JSONL, same discipline as the episodic layer):
 {subject, predicate, object, valid_from, valid_to|null}
 assert_temporal('', '', '', '2022-05-10', '2025-04-04')
 at_time('', '', '2020-06-01') -> fact
 current('', '') -> the open-interval fact

Honesty: a query outside every recorded interval returns None (never the
nearest guess); every answer carries its validity interval so the user SEES
the time slice that grounded it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FACTS_PATH = REPO / "data" / "graph_scale" / "temporal_facts.jsonl"


def assert_temporal(subject: str, predicate: str, obj: str, valid_from: str,
                    valid_to: str | None = None, source: str = "curated") -> dict[str, Any]:
    row = {"subject": subject.strip(), "predicate": predicate.strip(),
           "object": obj.strip(), "valid_from": str(valid_from)[:10],
           "valid_to": (str(valid_to)[:10] if valid_to else None),
           "source": source, "recorded": time.strftime("%Y-%m-%d")}
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FACTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _rows() -> list[dict[str, Any]]:
    if not FACTS_PATH.exists():
        return []
    out = []
    for line in FACTS_PATH.open(encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def at_time(subject: str, predicate: str, when: str) -> dict[str, Any] | None:
    """The fact valid at `when` (YYYY[-MM[-DD]]); None outside every interval."""
    w = str(when)[:10]
    if len(w) == 4:
        w += "-07-01"  # a bare year asks about mid-year
    best = None
    for r in _rows():
        if r["subject"] != subject or r["predicate"] != predicate:
            continue
        if r["valid_from"] <= w and (r["valid_to"] is None or w <= r["valid_to"]):
            if best is None or r["valid_from"] > best["valid_from"]:
                best = r
    return best


def current(subject: str, predicate: str) -> dict[str, Any] | None:
    return at_time(subject, predicate, time.strftime("%Y-%m-%d"))


def timeline_of(subject: str, predicate: str) -> list[dict[str, Any]]:
    hits = [r for r in _rows()
            if r["subject"] == subject and r["predicate"] == predicate]
    hits.sort(key=lambda r: r["valid_from"])
    return hits


def predicates_for(subject: str) -> list[str]:
    """Distinct predicates that have a timeline for this subject — so the answer
 bridge can match a query's role word without knowing the seed's predicate
 name in advance ( vs both resolve)."""
    return sorted({r["predicate"] for r in _rows() if r["subject"] == subject})


# Wikidata properties whose statements carry start/end qualifiers (P580/P582) —
# the mass supply line that turns 4D from one seeded timeline into a property
# of the whole graph. Same curated source discipline as the profile lane.
_TEMPORAL_PROPS = {"P35": "국가원수", "P6": "정부수반", "P169": "최고경영자",
                   "P488": "의장", "P36": "수도"}


def ingest_wikidata_timeline(term: str, log: Any = print) -> dict[str, Any]:
    """Pull the entity's TEMPORAL statements (with start/end qualifiers) from
    Wikidata and assert them as validity slices. Statements without a start
    qualifier are skipped — an interval we cannot ground is not recorded."""
    from .structured_profile import _api, _label_for, _resolve_qid

    out = {"term": term, "slices": 0}
    resolved = _resolve_qid(term)
    if not resolved:
        return out
    qid, _label = resolved
    try:
        data = _api(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    except Exception:
        return out
    claims = ((data.get("entities") or {}).get(qid) or {}).get("claims") or {}
    existing = {(r["predicate"], r["object"], r["valid_from"])
                for r in _rows() if r["subject"] == term}

    def _qual_time(claim: dict[str, Any], prop: str) -> str | None:
        for q in (claim.get("qualifiers") or {}).get(prop, []):
            t = ((q.get("datavalue") or {}).get("value") or {}).get("time") or ""
            if t and len(t) >= 11:
                return t[1:11].replace("-00", "-01")
        return None

    for prop, pred_ko in _TEMPORAL_PROPS.items():
        for claim in claims.get(prop, []):
            if claim.get("rank") == "deprecated":
                continue
            snak = claim.get("mainsnak") or {}
            if snak.get("snaktype") != "value":
                continue
            target_qid = str(((snak.get("datavalue") or {}).get("value") or {}).get("id") or "")
            if not target_qid:
                continue
            start = _qual_time(claim, "P580")
            if not start:
                continue  # ungrounded interval — honest skip
            end = _qual_time(claim, "P582")
            obj = _label_for(target_qid)
            if (pred_ko, obj, start) in existing:
                continue
            assert_temporal(term, pred_ko, obj, start, end, source=f"wikidata:{qid}")
            existing.add((pred_ko, obj, start))
            out["slices"] += 1
            log(f"  4D: {term} {pred_ko} {obj} [{start}~{end or '현재'}]")
    return out
