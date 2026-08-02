# -*- coding: utf-8 -*-
"""Append-only journal for the self-evolution orchestrator.

DOCTRINE (BINDING): every action the orchestrator takes — a weakness scan, a plan, a rejected
wireheading proposal — is journalled. The orchestrator DETECTS weakness and DISPATCHES/FLAGS loops;
it never silently rewrites the brain. The journal is the tamper-evident record of what it decided and
why, so an operator can audit the chain after the fact.

This module owns ONLY data/self_evolution/journal.jsonl. It writes append-only JSONL (one event per
line); it never rewrites or deletes history.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    """The ATANOR repo root (this file lives at <root>/packages/self_evolution/journal.py)."""
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = repo_root() / "data" / "self_evolution"
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_path() -> Path:
    return data_dir() / "journal.jsonl"


def record(event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append one journal event and return it. Never raises on a serialization edge — the record is
    coerced to a JSON-safe shape first so journaling can never itself crash an evolution tick."""
    rec = {"ts": round(time.time(), 3), "event": str(event), "payload": _safe(payload or {})}
    line = json.dumps(rec, ensure_ascii=False)
    with journal_path().open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return rec


def read_all() -> list[dict[str, Any]]:
    p = journal_path()
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _safe(x: Any) -> Any:
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {str(k): _safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_safe(v) for v in x]
    return str(x)
