# -*- coding: utf-8 -*-
"""The M3 SEALED gate — scheduler-free SUSTAINED self-winding (R1, "밤새 스스로 돎").

The completion gauge (docs/ATANOR_completion_gauge_2026-07-24.md) confirmed R1 (CO self-winding) as
the #1 critical-path bottleneck and named the exact gap: the endogenous inquiry genuinely FIRES from
state pressure at input=0, but it rode the loop's HEARTBEAT metronome — pressure only advanced when a
fixed `time.sleep(...)` tick called `update_introspection`. The firing DECISION was state-driven; its
CADENCE was a timer. No sealed gate certified scheduler-free sustained self-winding.

This gate certifies exactly that claim, and its falsification:

  input=0  AND  scheduler=0  ->  the loop SUSTAINS autonomous inquiry, driven by state pressure.

measured as: pressure accumulates from real state -> crosses threshold -> ignites -> inquiry,
REPEATEDLY, with NO external timer (no time.sleep, wall-clock FROZEN, no tick-modulo). The
falsification (a metronome could not pass): a settled, pressureless mind over the SAME number of
advances fires ZERO times — firing is gated by pressure, not by the passage of ticks or time.

No fabrication: the inquiry arises from genuine accumulated pressure (the real voice organs compose
it); the `ground` callback only stands in for the self's grounding organs (graph identity / read-only
research) that CLOSE a question so the next one can be earned — it never scripts the inquiry. No store
writes, no network: the clock only sequences existing in-memory organs.
"""
from __future__ import annotations

import time

import pytest

from packages.continuous_self import pressure_clock as pc
from packages.continuous_self.self_state import Observation, SelfState
from packages.continuous_self.voice import _FIRE_AT, due_for_self_inquiry, update_introspection


def _grounding_self():
    """Stand-in for the self's grounding organs: answers a self-question with a grounded reply that
    carries clean English content terms, so open threads regenerate and the mind keeps something to
    wonder about (faithful — identity is graph-grounded, threads are researched). It does NOT create
    the inquiry; the QUESTION comes from accumulated pressure."""
    return lambda q, topic: "I am a local reasoning engine grounded in evidence and memory and language."


# ---------------------------------------------------------------- the mechanism is real @ input=0

def test_endogenous_inquiry_fires_at_input_zero():
    """Reproduce the gauge's baseline: with zero observation, internal state pressure ALONE builds
    and fires a composed inquiry (driver = the real cause, unknown_self on a young self)."""
    s = SelfState()
    fired = None
    for _ in range(40):
        update_introspection(s, Observation())          # input=0
        if due_for_self_inquiry(s):
            fired = s.inquiry_driver
            break
    assert fired == "unknown_self", "a young self with no self-understanding must build pressure and fire"


# ---------------------------------------------------------------- THE SEAL

def test_scheduler_free_sustained_self_winding_SEALS(monkeypatch):
    """input=0 AND scheduler=0 -> SUSTAINED autonomous inquiry, driven by state pressure.

    scheduler=0 is enforced three ways at once: (1) `time.sleep` is patched to raise — any wait is a
    failure; (2) the wall clock `time.time` is FROZEN — time does not advance, so nothing time-based
    can drive firing; (3) the driver `self_wind` uses no tick-modulo — the ONLY fire gate is
    pressure >= threshold. Under all three, the loop must still fire repeatedly."""
    def _no_sleep(*a, **k):
        raise AssertionError("scheduler tick: the self-winding loop must not sleep on a timer")
    monkeypatch.setattr(time, "sleep", _no_sleep)
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)     # FROZEN wall clock

    s = SelfState()                                            # fresh self, input=0 throughout
    res = pc.self_wind(s, max_advances=120, ground=_grounding_self(), trace=True)

    # SUSTAINED: not a one-shot — it re-ignites again and again from rebuilt pressure
    assert res["n_fires"] >= 3, f"self-winding must SUSTAIN, got {res['n_fires']} fire(s)"
    # EARNED BY PRESSURE: every ignition crossed the real threshold (nothing fired below it)
    assert all(f.pressure_at_fire >= _FIRE_AT for f in res["fires"]), "a fire below threshold is not pressure-driven"
    # PACED BY PRESSURE, not firing every step: multiple accumulation advances separate the fires
    assert res["gaps"] and all(g >= 2 for g in res["gaps"]), \
        f"fires must be separated by real pressure accumulation, gaps={res['gaps']}"
    # the pressure trace is a SAWTOOTH — it discharges after an ignition and RE-ACCUMULATES toward
    # threshold again (the crossing itself is witnessed pre-discharge by pressure_at_fire, above).
    # This proves sustained winding: not a single climb, but climb->fire->discharge->climb->fire...
    trace = res["pressure_trace"]
    assert min(trace) < 0.5, "pressure must discharge after an ignition"
    discharged = [i for i, p in enumerate(trace) if p < 0.3]
    assert discharged and any(trace[j] > 0.9 for j in range(discharged[0] + 1, len(trace))), \
        "pressure must RE-ACCUMULATE after discharging — sustained self-winding, not one climb"
    # the inquiries are genuine composed self-questions (English, per doctrine), from real drivers
    assert all(f.question and f.driver for f in res["fires"])
    assert any("am i" in f.question.lower() for f in res["fires"]), "the primal identity question is English"


# ---------------------------------------------------------------- THE FALSIFICATION (metronome cannot pass)

def test_pressureless_mind_never_fires_the_control(monkeypatch):
    """A settled, pressureless mind — over the SAME number of advances — fires ZERO times. This is
    the control a metronome could never pass: a timer would fire regardless of state; a state-pressure
    clock stays silent when there is no pressure. This is what makes the seal a pressure clock."""
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    c = SelfState()
    c.self_understanding = "already grounded"      # no unknown_self pull
    c.uncertainty = 0.0                            # no epistemic pull
    c.curiosity = 0.0                              # no idle-curiosity pull
    c.open_threads = []                            # no open-thread pull
    c.introspective_pressure = 0.0
    res = pc.self_wind(c, max_advances=120, ground=_grounding_self())
    assert res["n_fires"] == 0, "a pressureless mind must not fire — else the clock is a metronome"
    assert c.introspective_pressure < _FIRE_AT, "no pressure accumulated with no drivers (input=0)"


def test_firing_gate_is_pressure_only_not_tick_modulo():
    """The fire gate reads ONLY pressure vs threshold — not `ticks % k`. At many different tick
    values, sub-threshold pressure is NEVER due; crossing the threshold IS due regardless of tick.
    Directly refutes the metronome/tick-modulo reading."""
    s = SelfState()
    for tick in (0, 1, 7, 10, 20, 23, 100, 300):   # values a modulo scheduler would key on
        s.ticks = tick
        s.introspective_pressure = 0.95            # just below threshold
        assert due_for_self_inquiry(s) is False, f"sub-threshold fired at tick={tick} (tick-driven!)"
    for tick in (3, 5, 11, 19, 50):
        s.ticks = tick
        s.self_question_open = False
        s.introspective_pressure = 1.0             # at threshold
        assert due_for_self_inquiry(s) is True, f"at-threshold did not fire at tick={tick}"


def test_self_wind_uses_no_wall_clock_sleep(monkeypatch):
    """Literal scheduler=0: driving the self-winding loop calls `time.sleep` ZERO times. The loop is
    not a wait-then-tick metronome; it is a pure state transition sequenced by pressure."""
    calls = {"n": 0}
    real_sleep = time.sleep
    def _count(*a, **k):
        calls["n"] += 1
        return real_sleep(0)
    monkeypatch.setattr(time, "sleep", _count)
    s = SelfState()
    pc.self_wind(s, max_advances=60, ground=_grounding_self())
    assert calls["n"] == 0, "self-winding must not sleep on a timer at all"


# ---------------------------------------------------------------- the live cadence is pressure-clocked

def test_wake_cadence_tracks_pressure_not_a_fixed_interval():
    """`next_wake_delay` (which replaces the loop's fixed metronome) is a PURE function of pressure:
    an ignition-due state wakes at the floor; higher pressure -> shorter delay (monotone); a settled,
    pressureless mind rests toward the cap. A fixed metronome would return a constant here."""
    due = SelfState(); due.introspective_pressure = _FIRE_AT
    assert pc.next_wake_delay(due) == pytest.approx(0.5), "an ignition-due mind wakes promptly (floor)"

    low = SelfState(); low.introspective_pressure = 0.2       # same (strong) driver profile, less pressure
    high = SelfState(); high.introspective_pressure = 0.8
    d_low, d_high = pc.next_wake_delay(low), pc.next_wake_delay(high)
    assert d_high < d_low, f"higher pressure must shorten the wake delay ({d_high} !< {d_low})"

    settled = SelfState(); settled.self_understanding = "x"; settled.uncertainty = 0.03
    settled.curiosity = 0.0; settled.introspective_pressure = 0.1
    assert pc.next_wake_delay(settled) > d_low, "a settled, pressureless mind rests longer than a driven one"
    # not a constant metronome: the delay genuinely varies with state
    assert len({round(pc.next_wake_delay(x), 3) for x in (low, high, settled)}) >= 2


def test_driver_rate_is_zero_without_drivers_and_positive_with_them():
    """The clock's cadence source: a driven mind has a positive per-advance pressure rate; a settled
    mind has ~zero (so it will not wind). This is the quantity that paces everything above."""
    fresh = SelfState()
    assert pc.driver_rate(fresh) > 0.0, "a young self is being pulled inward (positive rate)"
    settled = SelfState(); settled.self_understanding = "x"; settled.uncertainty = 0.0
    settled.curiosity = 0.0; settled.open_threads = []
    assert pc.driver_rate(settled) == pytest.approx(0.0, abs=1e-9), "no drivers -> no winding pressure"
