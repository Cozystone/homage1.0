# -*- coding: utf-8 -*-
"""Worm culture API — a living LIF colony ticking on ONE background thread.

GET /api/culture/state   -> current viz snapshot (generations, worms, voltages)
POST /api/culture/feed    -> nudge the world rhythm (interaction)
The colony runs itself on a daemon thread (one core, bounded, isolated). It is
an OBSERVATORY — wired to no store and no answer path.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/culture", tags=["culture"])

_CULTURE = None
_LOCK = threading.Lock()
_THREAD_STARTED = False


def _culture():
    global _CULTURE
    if _CULTURE is None:
        from packages.atanor_ecosystem.worm_culture import Culture

        _CULTURE = Culture(seed=7, n_neurons=24, start=2, cap=64)
        _CULTURE.seed_colony()
    return _CULTURE


def _run_loop() -> None:
    """Live the colony: tick its neural dynamics, breed a generation now and then.
    Bounded, single background thread, ~4 Hz — cheap on one core."""
    import os

    if os.environ.get("ATANOR_DISABLE_DAEMON_SELF_HEAL"):
        return  # tests / CI: no background life
    gen_every = 0
    while True:
        try:
            with _LOCK:
                _culture().tick(ticks=12)
                gen_every += 1
                if gen_every >= 8:  # breed a new generation every ~2s
                    _culture().breed_generation()
                    gen_every = 0
        except Exception:
            pass
        time.sleep(0.25)


def _ensure_thread() -> None:
    global _THREAD_STARTED
    if not _THREAD_STARTED:
        with _LOCK:
            if not _THREAD_STARTED:
                t = threading.Thread(target=_run_loop, daemon=True, name="worm-culture")
                t.start()
                _THREAD_STARTED = True


@router.get("/state")
def culture_state() -> dict[str, Any]:
    _ensure_thread()
    with _LOCK:
        return _culture().snapshot()


@router.post("/feed")
def culture_feed(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Interaction: an immediate burst of ticks (feed the colony energy/rhythm)."""
    _ensure_thread()
    with _LOCK:
        return _culture().tick(ticks=int(body.get("ticks", 40)))
