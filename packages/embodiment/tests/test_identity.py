# -*- coding: utf-8 -*-
"""Track E M4s — the autobiographical ledger must stay self-consistent over a real embodied life:
one arrow of time, no effect-before-cause, and self/world never confused. Skipped without mujoco."""
from __future__ import annotations

import pytest

from packages.embodiment.identity import IdentityLedger

pytest.importorskip("mujoco")

from packages.embodiment.identity import run_embodied_life


def test_ledger_is_time_ordered_and_causally_valid():
    led = IdentityLedger()
    a = led.record(1, "contact", "touched floor", "me")
    b = led.record(3, "surprise", "startled by a shove", "world", surprise=0.9, cause=a)
    c = led.record(5, "affordance", "can push box", "me", reward=0.8, cause=b)
    rep = led.consistency()
    assert rep["consistency"] == 1.0                 # monotone time + valid causes + clean ownership
    assert led.episodes[c].hormones[2] > 0           # dopamine rose on the reward


def test_embodied_life_writes_a_consistent_autobiography():
    r = run_embodied_life(steps=500, seed=1)
    assert r["consistency"]["episodes"] >= 2         # a life produced salient episodes
    assert r["consistency"]["consistency"] >= 0.9    # M4s gate: the narrative does not contradict itself
    assert r["self_episodes"] >= 1 and r["world_episodes"] >= 1   # both self- and world-caused events


def test_hormone_signature_binds_to_experience():
    # a surprise raises adrenaline; the ledger carries the felt signature with the memory.
    led = IdentityLedger()
    led.record(1, "contact", "resting", "me")
    idx = led.record(2, "surprise", "sudden shove", "world", surprise=1.0)
    assert led.episodes[idx].hormones[0] > led.episodes[0].hormones[0]   # adrenaline spiked
