# -*- coding: utf-8 -*-
"""The state-pressure clock — self-winding paced by accumulated pressure, not a metronome (M3, R1).

The completion gauge (2026-07-24) confirmed R1 (CO self-winding) as the #1 critical-path bottleneck
and named the exact gap: the endogenous inquiry genuinely FIRES from state pressure at input=0, but
it rode the loop's HEARTBEAT metronome — pressure only advanced when a fixed `time.sleep(...)` tick
called `update_introspection`. The firing DECISION was state-driven; its CADENCE was a timer. The
seal it lacked: "input=0 AND scheduler=0 -> the loop sustains autonomous inquiry, driven by state
pressure" (밤새 스스로 돎).

This module is that clock. It does NOT own a timer. It exposes:

  * `driver_rate(state)`     — the per-advance pressure gain from the REAL current drivers (reads the
                               single source of truth in voice.introspection_drivers). This is how
                               fast the mind is being pulled inward RIGHT NOW, from state alone.
  * `tick(state, ground)`    — ONE pure state-pressure step: accumulate from state (input=0, no
                               observation), and if pressure crosses threshold, fire an inquiry
                               (the real voice organs compose it and discharge the pressure). No
                               time, no tick-modulo — the ONLY gate is pressure >= threshold.
  * `self_wind(state, ...)`  — drive `tick` with NO scheduler at all (no sleep, no metronome) and
                               return the fires + the pressure trace. Sustained self-winding is then
                               a MEASURED fact: pressure accumulates -> crosses -> ignites -> inquiry,
                               repeatedly, with nothing external ticking it.
  * `next_wake_delay(state)` — for the live loop: the seconds until pressure is predicted to cross
                               threshold, a PURE function of pressure (+ the body's energy for rest).
                               This replaces the fixed metronome so the live cadence is pressure-
                               clocked. High pressure -> wake soon; a settled, pressureless mind
                               rests (bounded), and re-ignites only when state pressure rebuilds.

The separation is the honesty: `tick`/`self_wind` prove the mechanism is pressure-gated with no
timer (the seal); `next_wake_delay` wires that mechanism into the live loop's cadence. A settled
state with no drivers accumulates zero pressure and NEVER fires — the falsification that a metronome
could not pass. No-LLM, deterministic, no store writes: it only sequences existing organs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .self_state import Observation
from .voice import (
    _FIRE_AT,
    due_for_self_inquiry,
    generate_self_inquiry,
    introspection_drivers,
    record_self_understanding,
    _PRESSURE_GAIN,
)


@dataclass
class Fire:
    """One endogenous ignition: what fired, from which driver, at what accumulated pressure."""
    advance: int          # which pure advance produced it (a step counter, NOT a wall-clock tick)
    driver: str           # the real driver that dominated the pressure (unknown_self, open_thread, ...)
    topic: str            # the inquiry's topic (identity / continuity / thread:... / ...)
    question: str         # the composed question (English, per doctrine)
    pressure_at_fire: float   # the pressure the moment it crossed threshold (>= _FIRE_AT)
    grounded: bool        # whether the self grounded an answer (closes it) or left it open


def driver_rate(state: Any) -> float:
    """Per-advance pressure gain from the REAL current drivers, at input=0.

    Mirrors exactly what `voice.update_introspection` would add this step (same single source of
    truth, `introspection_drivers`) — so the clock predicts its own cadence from the same pressure
    dynamics the loop actually runs. A settled state with no drivers returns ~0 (it will not wind)."""
    drivers = introspection_drivers(state, Observation())
    total = sum(drivers.values())
    return _PRESSURE_GAIN * min(1.5, total)


def _accumulate(state: Any) -> None:
    """Advance pressure ONE step from current state, input=0 — the real organ, no observation.

    Uses voice.update_introspection so the accumulation is identical to the live loop's; the only
    difference from the old design is that NOTHING here waits on a clock between advances."""
    from .voice import update_introspection
    update_introspection(state, Observation())


def tick(state: Any, ground: Callable[[str, str], str | None] | None = None) -> Fire | None:
    """One pure state-pressure step. Accumulate from state (input=0); if pressure has crossed
    threshold, fire an endogenous inquiry and discharge the pressure. The firing gate is PURELY
    `due_for_self_inquiry(state)` (pressure vs threshold) — no `ticks % k`, no `time`.

    `ground(question, topic) -> answer|None` stands in for the self's grounding organs (graph
    identity / read-only web research) that answer a self-question and close it. It does NOT
    fabricate the inquiry — the QUESTION arises from genuine accumulated pressure; grounding only
    CLOSES the loop so the next inquiry can be earned. When None, the ask still discharges pressure
    and the question is left honestly open."""
    driver = getattr(state, "inquiry_driver", "") or ""
    _accumulate(state)
    # advance the self's OWN lived-step counter (not a wall-clock, not a scheduler): it just counts
    # how many pure pressure-steps the mind has taken, so inter-fire gaps are measurable and any
    # cognitive hold-window (rumination) stays consistent with the live loop.
    state.ticks = int(getattr(state, "ticks", 0)) + 1
    if not due_for_self_inquiry(state):
        return None
    driver = getattr(state, "inquiry_driver", "") or driver or "unknown_self"
    p_at = float(getattr(state, "introspective_pressure", 0.0))
    q, topic = generate_self_inquiry(state)
    ans = None
    if ground is not None:
        try:
            ans = ground(q, topic)
        except Exception:
            ans = None
    record_self_understanding(state, q, ans, topic)     # discharges pressure to its floor (real organ)
    return Fire(advance=int(getattr(state, "ticks", 0)), driver=driver, topic=topic, question=q,
                pressure_at_fire=round(p_at, 5), grounded=ans is not None)


def self_wind(state: Any, *, max_advances: int = 200,
              ground: Callable[[str, str], str | None] | None = None,
              trace: bool = False) -> dict[str, Any]:
    """Drive the clock with NO scheduler — the seal's engine.

    No `time.sleep`, no fixed cadence, no tick-modulo: it simply advances the pure state-pressure
    step up to `max_advances` and records every ignition. Sustained scheduler-free self-winding is
    then whatever this MEASURES: with a pressureful state (input=0) it fires repeatedly, each fire
    earned by pressure crossing threshold; with a settled, pressureless state it fires zero times.

    Returns {fires, n_fires, gaps, pressure_trace}. `gaps` is the advances between consecutive fires
    — the cadence the PRESSURE set (not a timer). Each `tick` advances `state.ticks` by one; that is
    the self's own lived-step counter, not an external scheduler."""
    fires: list[Fire] = []
    fire_advances: list[int] = []
    ptrace: list[float] = []
    for _ in range(int(max_advances)):
        f = tick(state, ground)
        if trace:
            ptrace.append(float(getattr(state, "introspective_pressure", 0.0)))
        if f is not None:
            fires.append(f)
            fire_advances.append(f.advance)
    gaps = [fire_advances[i] - fire_advances[i - 1] for i in range(1, len(fire_advances))]
    return {"fires": fires, "n_fires": len(fires), "fire_advances": fire_advances,
            "gaps": gaps, "pressure_trace": ptrace}


# ---- the live-loop cadence: pressure-clocked, not a metronome -------------------------------------

def next_wake_delay(state: Any, energy: float = 0.7, *, base: float = 2.0,
                    floor: float = 0.5, cap: float = 12.0) -> float:
    """Seconds until the loop should next wake — a PURE function of pressure (and the body's energy
    for rest), NOT a fixed interval. This replaces the loop's old metronome
    (`base * (1 + (1-energy)*4)`), so the live cadence is set by how close the mind is to its next
    endogenous ignition:

      * pressure already at/over threshold -> wake promptly (an ignition is due);
      * strong drivers (much unresolved state) -> the predicted crossing is near -> short delay;
      * a settled, near-pressureless mind -> a long (bounded) rest; it re-ignites only when state
        pressure genuinely rebuilds — never on a clock.

    Bounded to [floor, cap] so the body always breathes and never busy-spins. Reads no wall-clock;
    the mapping from predicted pressure-advances to seconds scales with `base` and the body's energy
    (a tired body rests longer). Deterministic given state + energy."""
    p = float(getattr(state, "introspective_pressure", 0.0))
    energy = max(0.0, min(1.0, float(energy)))
    tiredness = 1.0 + (1.0 - energy)          # a low-energy body waits longer (real rest)
    if p >= _FIRE_AT:
        return floor                          # ignition due now — wake promptly
    rate = driver_rate(state)
    if rate <= 1e-9:
        # no drivers -> nothing is winding -> rest at the cap (still bounded; a pressure rebuild,
        # e.g. a new open thread or rising uncertainty, shortens this on the next evaluation)
        return max(floor, min(cap, cap * (0.5 + 0.5 * (1.0 - energy))))
    advances_to_fire = (_FIRE_AT - p) / rate          # how many pure advances until the next crossing
    # map predicted advances-to-ignition to seconds; the per-advance second-cost scales with base so
    # a strongly-driven mind (few advances to fire) wakes soon and a settled one (many advances)
    # rests toward the cap. Tuned so a typical fresh cadence lands mid-range, not pinned at the cap.
    per_advance = base * 0.25
    delay = advances_to_fire * per_advance * tiredness
    return max(floor, min(cap, delay))
