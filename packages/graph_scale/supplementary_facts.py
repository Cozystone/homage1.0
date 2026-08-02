# -*- coding: utf-8 -*-
"""Read-only VERIFIED-fact overlay (owner-directed 2026-07-18). The world-pack build stopped early
and misses major-entity facts entirely ( has no capital edge at all). `backfill_supplementary_
facts.py` fetches those from Wikidata (sourced) into data/graph_scale/supplementary_facts.jsonl;
this serves them at read time as a supplement to the store.

SIDECAR discipline — nothing is written to the triple store (): every row carries its
Wikidata source, delete the file and the overlay is gone, the graph unchanged. It only ADDS facts
the store is missing; it never overrides a store fact (the store stays the primary).
"""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "supplementary_facts.jsonl"
_BY_SUBJECT: dict[str, list[dict]] | None = None
_SIG: tuple[float, int] | None = None


def _sig() -> tuple[float, int]:
    try:
        st = _PATH.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, 0)


def _load() -> dict[str, list[dict]]:
    global _BY_SUBJECT, _SIG
    sig = _sig()
    if _BY_SUBJECT is not None and _SIG == sig:
        return _BY_SUBJECT
    by: dict[str, list[dict]] = {}
    if _PATH.exists():
        with _PATH.open(encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("subject") and r.get("relation"):
                    by.setdefault(r["subject"], []).append(r)
    _BY_SUBJECT, _SIG = by, sig
    return by


def facts_for(subject: str, relation: str | None = None) -> list[dict]:
    """Verified supplementary rows for `subject` (optionally filtered to `relation`). Each row:
    {subject, relation, object: [labels...], source}. Empty when the overlay has nothing."""
    rows = _load().get(str(subject), [])
    if relation is None:
        return list(rows)
    return [r for r in rows if r["relation"] == relation]


def size() -> int:
    return sum(len(v) for v in _load().values())
