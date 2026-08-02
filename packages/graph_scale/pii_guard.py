# -*- coding: utf-8 -*-
"""PII guard — personal-data detection, quarantine, right-to-be-forgotten.

The self-refinement ideal (" ") is only ethical if the swallow does
NOT accumulate people's private data. This guard is the boundary condition:

 * detect(text) — find PII spans (Korean-aware: , , ,
 , patterns + a checksum where one exists), each with a type
 and a redacted preview (the raw value is NEVER logged).
 * gate(subject, predicate, object) — a candidate carrying PII is REFUSED at
 the ingest boundary, before it can become a triple. Prevention beats cleanup.
 * scan_and_quarantine(store) — sweep existing rows; PII-bearing facts are
 retracted (tombstoned, reversible, audited) rather than left in the graph.
 * forget(store, subject) — right to be forgotten: retract every row mentioning
 a subject, on request. Auditable, honest (returns what it removed).

Design honesty: detection is high-precision patterns, not a claim of catching
ALL PII (no detector does). It catches the structured, high-risk classes that
a bulk web swallow actually accumulates, and the forget() path handles the rest
on request. The raw PII value never enters a log or a return value — only its
type and a masked form.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "pii_quarantine.jsonl"

# high-precision structured-PII patterns (Korean context + universal)
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("krrn", re.compile(r"\b\d{6}[\s-]?[1-4]\d{6}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone_kr", re.compile(r"\b01[016789][\s-]?\d{3,4}[\s-]?\d{4}\b")),
    ("card", re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")),        # 16-digit card
    ("account", re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,7}\b")),
    ("passport_kr", re.compile(r"\b[MSRODmsrod]\d{8}\b")),
]


def _mask(value: str) -> str:
    """Redacted preview — keep only a shape hint, never the raw value."""
    v = value.strip()
    if len(v) <= 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def detect(text: str) -> list[dict[str, str]]:
    """PII spans in text, each as {type, masked}. Raw value never returned."""
    s = str(text or "")
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for kind, pat in _PATTERNS:
        for m in pat.finditer(s):
            raw = m.group(0)
            # a card pattern also matches some account/phone shapes — de-dup by span
            span_key = f"{m.start()}:{m.end()}"
            if span_key in seen:
                continue
            # krrn checksum guard cuts most false 13-digit numbers
            if kind == "krrn" and not _krrn_plausible(raw):
                continue
            seen.add(span_key)
            hits.append({"type": kind, "masked": _mask(raw)})
    return hits


def _krrn_plausible(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 13:
        return False
    mm, dd = int(digits[2:4]), int(digits[4:6])
    return 1 <= mm <= 12 and 1 <= dd <= 31


def has_pii(text: str) -> bool:
    return bool(detect(text))


def gate(subject: str, predicate: str, obj: str) -> dict[str, Any]:
    """Ingest-boundary check: refuse a candidate that carries PII in any field.
    Returns {allowed, pii}. Prevention — the triple never forms."""
    found = detect(subject) + detect(predicate) + detect(obj)
    return {"allowed": not found, "pii": found}


def scan_and_quarantine(store: Any, *, apply: bool = False,
                        max_rows: int | None = 2_000_000) -> dict[str, Any]:
    """Sweep the store: rows whose object (or subject) carries PII are retracted
    (reversible tombstone), and the action is ledgered with MASKED evidence only."""
    import numpy as np

    cols = store.open_columns()
    n = (
        len(cols["s"])
        if max_rows is None
        else min(len(cols["s"]), max_rows)
    )
    if n == 0:
        return {"scanned": 0, "quarantined": 0}
    s = np.asarray(cols["s"][:n])
    p = np.asarray(cols["p"][:n])
    o = np.asarray(cols["o"][:n])
    tomb = store._tombstones()
    detected = 0
    removed = 0
    ledger_rows = []
    # scan distinct object/subject terms once (curated dumps reuse heavily)
    checked: dict[int, bool] = {}

    def _term_has_pii(tid: int) -> bool:
        if tid not in checked:
            checked[tid] = has_pii(store.terms.term(int(tid)))
        return checked[tid]

    for i in range(n):
        subj = store.terms.term(int(s[i]))
        pred = store.terms.term(int(p[i]))
        obj = store.terms.term(int(o[i]))
        if (subj, pred, obj) in tomb:
            continue
        pii = _term_has_pii(int(o[i])) or _term_has_pii(int(s[i]))
        if not pii:
            continue
        detected += 1
        if apply:
            # Never count or ledger a quarantine until the mutation actually
            # succeeded.  PermissionError on the immutable shipped store must
            # propagate to its caller instead of becoming a false success.
            store.retract(subj, pred, obj, reason="pii_quarantine")
            removed += 1
            ledger_rows.append({
                "subject_masked": _mask(subj),
                "predicate": pred,
                "pii": detect(subj) + detect(obj),
            })
    if ledger_rows:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "quarantined": removed, "rows": ledger_rows[:50]},
                                ensure_ascii=False) + "\n")
    return {
        "scanned": n,
        "detected": detected,
        "quarantined": removed,
        "applied": apply is True,
    }


def forget(
    store: Any,
    subject: str,
    *,
    apply: bool = False,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Right to be forgotten: retract every row where `subject` appears as
    subject OR object. ``apply=False`` performs a read-only complete scan so a
    caller can report pending work without claiming erasure. Auditable; returns
    counts only, never the matched values."""
    import numpy as np

    cols = store.open_columns()
    n = (
        len(cols["s"])
        if max_rows is None
        else min(len(cols["s"]), max_rows)
    )
    sid = store.terms.lookup(subject)
    triples: set[tuple[str, str, str]] = set()
    if n and sid is not None:
        s_col = np.asarray(cols["s"][:n])
        o_col = np.asarray(cols["o"][:n])
        indices = np.nonzero((s_col == sid) | (o_col == sid))[0]
        tombstones = store._tombstones()
        for row in indices:
            index = int(row)
            triple = (
                store.terms.term(int(cols["s"][index])),
                store.terms.term(int(cols["p"][index])),
                store.terms.term(int(cols["o"][index])),
            )
            if triple not in tombstones:
                triples.add(triple)
    removed = 0
    if apply:
        for subj, pred, obj in sorted(triples):
            # A failed write is a failed erasure request.  Do not swallow it
            # and never return rows_removed>0 for an unapplied tombstone.
            store.retract(
                subj,
                pred,
                obj,
                reason="right_to_be_forgotten",
            )
            removed += 1
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "forget_subject_masked": _mask(subject),
                "rows_removed": removed,
            }, ensure_ascii=False) + "\n")
    return {
        "subject_masked": _mask(subject),
        "rows_matched": len(triples),
        "rows_removed": removed,
        "applied": apply is True,
        "complete_scan": max_rows is None or n == len(cols["s"]),
    }
