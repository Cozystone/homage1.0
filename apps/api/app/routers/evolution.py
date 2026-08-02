# -*- coding: utf-8 -*-
"""Evolution world API — a chemotaxis colony evolving on ONE background thread.

GET  /api/evolve/state  -> viz snapshot (worms with x,y,heading,fitness,color; food)
POST /api/evolve/feed   -> drop a burst of food (interaction)
POST /api/evolve/crispr -> operator gene-edit: nudge the elite's wiring (manual mutation)

The world runs itself: worms must navigate a chemical gradient to food or starve,
survivors breed, the finish line moves. One daemon thread, bounded, isolated —
observatory only, wired to no store and no answer path.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/evolve", tags=["evolve"])

_WORLD = None
_LOCK = threading.Lock()
_THREAD_STARTED = False


def _world():
    global _WORLD
    if _WORLD is None:
        from packages.atanor_ecosystem.evolution_world import World

        _WORLD = World(seed=11, n_neurons=24, start=6, cap=48,
                       width=120.0, height=70.0, food_density=22)
        _WORLD.seed_world()
    return _WORLD


def _run_loop() -> None:
    import os

    if os.environ.get("ATANOR_DISABLE_DAEMON_SELF_HEAL"):
        return
    gen_every = 0
    while True:
        try:
            with _LOCK:
                _world().tick(steps=4)
                gen_every += 1
                if gen_every >= 40:          # breed a generation ~every 8s of crawling
                    _world().breed_generation()
                    gen_every = 0
        except Exception:
            pass
        time.sleep(0.2)


def _ensure_thread() -> None:
    global _THREAD_STARTED
    if not _THREAD_STARTED:
        with _LOCK:
            if not _THREAD_STARTED:
                t = threading.Thread(target=_run_loop, daemon=True, name="evolve-world")
                t.start()
                _THREAD_STARTED = True


@router.get("/state")
def evolve_state() -> dict[str, Any]:
    _ensure_thread()
    with _LOCK:
        return _world().snapshot()


@router.post("/feed")
def evolve_feed(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Drop a cluster of rich food at a point (default centre) — interaction."""
    _ensure_thread()
    with _LOCK:
        w = _world()
        from packages.atanor_ecosystem.evolution_world import Food

        cx = float(body.get("x", w.width / 2))
        cy = float(body.get("y", w.height / 2))
        for _ in range(int(body.get("count", 8))):
            w.food.append(Food(x=cx + w._rng.uniform(-8, 8),
                               y=cy + w._rng.uniform(-8, 8), amount=2.4))
        return w.snapshot()


@router.post("/crispr")
def evolve_crispr(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Operator 'CRISPR' edit: force a burst of structural mutations on the elite,
    injecting variation by hand when nature isn't throwing enough. Additive, never
    destructive — it rewires copies, it does not delete lineages."""
    _ensure_thread()
    with _LOCK:
        w = _world()
        rng = w._rng
        alive = sorted([x for x in w.worms if x.alive], key=lambda x: -x.fitness)
        edits = int(body.get("edits", 3))
        for wm in alive[: max(1, int(body.get("targets", 4)))]:
            for _ in range(edits):
                i = rng.randrange(wm.n)
                wm.syn[i] = [rng.randrange(wm.n) for _ in range(len(wm.syn[i]))]
        return w.snapshot()
