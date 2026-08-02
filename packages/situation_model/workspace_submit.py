# -*- coding: utf-8 -*-
"""Situation model -> workspace submission (GWT-1 wiring, the second heavy module).

The completion gauge (2026-07-24) found the ignition workspace ran on a blind seat: the heavy
parallel modules (vision, situation_model) did not SUBMIT. This is the situation_model half — a
standing register of the LAST world the model built from text, handed to the workspace so the
current situation competes as a `situation` candidate.

Unlike vision, situation_model is NOT always-on: it only builds a world when there is text to read.
So it submits only when it has a RECENTLY-built situation (`note_situation` is called at the end of
`builder.build`), and reports nothing when there is no current situation (honest — no fabricated
world). The salience reflects how much structure the situation carries (entities + events); the
topic is the dominant actor, so the workspace attends to WHO the current world is about.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_LATEST: dict[str, Any] = {}

# a built situation is the "current world" for this long; after it, there is no current situation
# (the model is not holding a stale world as if it were now).
_FRESH_S = 300.0


def note_situation(sit: Any, now: float | None = None) -> None:
    """Called at the end of builder.build — register the world just built as the current situation.

    Reads only the public shape of a Situation (entities/events/actors); tolerant of any object so
    the builder never breaks if the summary shape changes. An empty situation registers nothing."""
    now = time.time() if now is None else now
    try:
        entities = getattr(sit, "entities", {}) or {}
        events = getattr(sit, "events", []) or []
        actors = sit.actors() if hasattr(sit, "actors") else sorted(entities)
        n_ent, n_ev = len(entities), len(events)
        if n_ent == 0 and n_ev == 0:
            return                                  # no world was built — submit nothing (honest)
        topic = (actors[0] if actors else "situation")
        with _LOCK:
            _LATEST.clear()
            _LATEST.update({
                "topic": str(topic)[:40],
                "entities": int(n_ent),
                "events": int(n_ev),
                "at": float(now),
            })
    except Exception:
        # registering a percept must never break the build path
        pass


def clear() -> None:
    with _LOCK:
        _LATEST.clear()


def current_percept(now: float | None = None) -> dict[str, Any] | None:
    """The CURRENT situation as a workspace submission, or None if there is no current world.

    Salience grows with the structure the situation carries (more entities + events = a richer,
    more attention-worthy world), bounded. Returns None when nothing was built recently — the model
    honestly has no current situation rather than submitting a stale or empty one."""
    now = time.time() if now is None else now
    with _LOCK:
        snap = dict(_LATEST)
    if not snap or (now - float(snap.get("at", 0.0))) > _FRESH_S:
        return None
    structure = int(snap.get("entities", 0)) + int(snap.get("events", 0))
    if structure <= 0:
        return None
    salience = max(0.30, min(0.80, 0.30 + 0.06 * structure))
    return {
        "topic": str(snap.get("topic", "situation"))[:40],
        "salience": round(salience, 4),
        "entities": int(snap.get("entities", 0)),
        "events": int(snap.get("events", 0)),
    }
