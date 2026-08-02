# -*- coding: utf-8 -*-
"""Vision -> workspace submission (GWT-1 wiring).

The gap the completion gauge (2026-07-24) named: the heavy parallel perceptual modules —
vision, situation_model — EXIST and run, but they never actually SUBMIT their percept to the
ignition workspace, so the global-workspace competition ran on a blind seat (utterance / vital /
curiosity only). "Parallel existence yes, parallel submission only partial."

This is the vision half of the fix: a standing visual channel that always carries its CURRENT
percept and hands it to whoever gathers the workspace's competing candidates. Faithful to GWT —
a specialist module continuously submits its current output; when the field is quiet it submits a
low-salience "quiet field" percept (and loses the competition), which is exactly parallel
SUBMISSION, not a fabricated content. Honesty contract: the percept reports the REAL state of the
visual channel. The salience is the real prediction-error (change energy) of the last frame; when
no live frame has been processed it honestly reports `live=False` (a standing field, nothing
salient) rather than inventing objects.

No heavy deps: this is a tiny module-level register updated by the live perception path
(`note_frame`) and read by the workspace tap (`current_percept`). The expensive detector
(open_vocab / OWLv2) is never imported here.
"""
from __future__ import annotations

import threading
import time
from typing import Any

# process-lifetime register of the current visual percept. A single standing channel — the
# module is always "looking"; this holds what it currently sees. Guarded so the live perception
# thread and the workspace-gather thread never race.
_LOCK = threading.Lock()
_LATEST: dict[str, Any] = {}

# a real frame's percept is considered "current" for this long; after it, the channel reports the
# standing quiet field again (the last thing seen has gone stale — honest, not a frozen memory).
_FRESH_S = 20.0
# the standing quiet field still SUBMITS (vision is always on), but at a floor salience so it loses
# to any real content. This is "I am looking; nothing salient", not fabricated content.
_QUIET_SALIENCE = 0.03


def note_frame(*, energy: float, label: str = "", objects: int = 0, now: float | None = None) -> None:
    """The live perception path calls this when it processes a frame (after the attention gate).

    `energy` is the real prediction-error / change-energy in [0,1] (see attention.change_energy) —
    it becomes the percept's salience, so a scene that just changed competes loudly and a static
    scene barely at all. `label` is the dominant detected object if the heavy detector ran (else
    empty -> the topic is the generic visual field). Nothing is invented: an empty read stays empty.
    """
    now = time.time() if now is None else now
    with _LOCK:
        _LATEST.clear()
        _LATEST.update({
            "energy": max(0.0, min(1.0, float(energy))),
            "label": str(label or "").strip(),
            "objects": int(objects),
            "at": float(now),
            "live": True,
        })


def clear() -> None:
    """Drop the current percept (channel reset / test isolation)."""
    with _LOCK:
        _LATEST.clear()


def current_percept(now: float | None = None) -> dict[str, Any]:
    """The visual channel's CURRENT percept, as a workspace submission.

    Always returns a percept (vision is a standing, always-on channel): a fresh real frame if one
    was processed recently, otherwise the honest quiet standing field (`live=False`). The caller
    (ignition.gather_candidates) turns this into a `percept` Candidate so vision actually competes
    in the global workspace. Salience is the real change-energy; topic is the detected object when
    there is one, else the generic visual field."""
    now = time.time() if now is None else now
    with _LOCK:
        snap = dict(_LATEST)
    fresh = snap.get("live") and (now - float(snap.get("at", 0.0))) <= _FRESH_S
    if fresh:
        label = snap.get("label") or "visual_field"
        # salience floored so a barely-changed but real frame still submits above pure quiet
        salience = max(_QUIET_SALIENCE, min(0.98, float(snap.get("energy", 0.0))))
        return {
            "topic": str(label)[:40],
            "salience": round(salience, 4),
            "live": True,
            "energy": round(float(snap.get("energy", 0.0)), 4),
            "objects": int(snap.get("objects", 0)),
        }
    # standing quiet field — honestly reports no live frame; still SUBMITS (parallel submission)
    return {
        "topic": "visual_field",
        "salience": _QUIET_SALIENCE,
        "live": False,
        "energy": 0.0,
        "objects": 0,
    }
