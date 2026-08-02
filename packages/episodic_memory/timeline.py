# -*- coding: utf-8 -*-
"""Episodic time-axis graph v0 — Phase 3-1, the 's memory substrate.

The knowledge graph knows WHAT things are; this layer remembers WHEN things
happened to WHOM: possessions, purchases, events — triples with a time axis.
' 3 ' .

Design (local-first, append-only, auditable — the local-brain contract):
 record_event('', '', '', at='2023-07-08', note=' 500ml')
 age_days('', '', '') -> 1095
 timeline('') -> every event touching the entity
 repurchase_suggestion('', 900) -> the scenario's reasoning primitive

All data stays in data/episodic/events.jsonl on THIS machine. Nothing here is
fabricated: an age is computed from a recorded timestamp or not at all.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EVENTS_PATH = REPO / "data" / "episodic" / "events.jsonl"


def _parse_at(at: str | None) -> str:
    if not at:
        return time.strftime("%Y-%m-%d")
    return str(at)[:10]


def record_event(subject: str, predicate: str, obj: str, at: str | None = None,
                 note: str = "", source: str = "user") -> dict[str, Any]:
    """Append one dated event. `at` accepts YYYY-MM-DD (past events welcome —
 '3 ' records the real purchase date, not today)."""
    row = {"at": _parse_at(at), "recorded": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "subject": subject.strip(), "predicate": predicate.strip(),
           "object": obj.strip(), "note": note.strip(), "source": source}
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _rows() -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    out = []
    for line in EVENTS_PATH.open(encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def timeline(entity: str, limit: int = 20) -> list[dict[str, Any]]:
    """Every event touching the entity (as subject or object), oldest first."""
    hits = [r for r in _rows()
            if entity in (r.get("subject"), r.get("object"))
            or entity in str(r.get("object") or "")]
    hits.sort(key=lambda r: r.get("at") or "")
    return hits[:limit]


def age_days(subject: str, predicate: str, obj: str) -> int | None:
    """Days since the MOST RECENT matching event; None when never recorded —
    an unknown age is never guessed."""
    best: str | None = None
    for r in _rows():
        if (r.get("subject") == subject and r.get("predicate") == predicate
                and obj in str(r.get("object") or "")):
            if best is None or str(r.get("at")) > best:
                best = str(r.get("at"))
    if best is None:
        return None
    try:
        then = datetime.strptime(best, "%Y-%m-%d").date()
        return (date.today() - then).days
    except Exception:
        return None


def repurchase_suggestion(obj: str, threshold_days: int = 900,
                          subject: str = "사용자") -> dict[str, Any] | None:
    """The primitive: if the user's possession is older than the threshold,
 return a grounded suggestion (with the REAL age and the source event) —
 otherwise None. Nothing is suggested without a recorded basis."""
    days = age_days(subject, "구매", obj)
    if days is None:
        days = age_days(subject, "소유", obj)
    if days is None or days < threshold_days:
        return None
    years = days // 365
    when = f"약 {years}년" if years >= 1 else f"{days}일"
    return {
        "object": obj,
        "age_days": days,
        "suggestion": (f"집에 있는 {obj}을(를) 구매한 지 {when} 됐어요. "
                       f"이 참에 하나 더 마련하는 건 어떨까요?"),
        "basis": timeline(obj, limit=3),
    }
