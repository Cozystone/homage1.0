# -*- coding: utf-8 -*-
"""Live thought — the bridge from the answer path to the orb's imagination.

When ATANOR answers, it stashes WHAT it just thought about (the query) here — a single cheap write
on the POST-answer chokepoint, so the conversation's latency is never touched. The orb polls
/api/imagination/current, which compiles a graph-grounded scene from this stash and renders it as
live particles. Freshness-gated: an old thought fades, so the orb shows only the *current* mind.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[2] / "data" / "imagination" / "live_thought.json"


def set_thought(query: str, *, answer_kind: str = "", subject: str | None = None,
                evidence: list[str] | None = None, mode: str = "thought",
                place: str | None = None) -> None:
    """Record the current thought — best-effort, never raises into the answer path. `evidence` is
    the answer's own evidence-concept names (what it ACTUALLY reasoned over). `mode` is normally
    'thought'; 'replay' means the mind is recalling a remembered SPACE (place = which one), so the
    orb rebuilds that space instead of the concept scene."""
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps({
            "query": str(query or "")[:200], "at": round(time.time(), 2),
            "answer_kind": str(answer_kind or "")[:40], "subject": subject,
            "evidence": [str(e)[:80] for e in (evidence or [])][:12],
            "mode": "replay" if mode == "replay" else "thought", "place": place,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def get_thought(max_age_s: float = 45.0) -> dict[str, Any] | None:
    """The latest thought, or None if there is none fresher than max_age_s (the mind goes quiet)."""
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        if time.time() - float(d.get("at", 0)) <= max_age_s and str(d.get("query") or "").strip():
            return d
    except Exception:
        pass
    return None
