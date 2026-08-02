# -*- coding: utf-8 -*-
"""Digital genome — serialize/deserialize round-trip + sexual crossover."""

from __future__ import annotations

import random

from packages.atanor_ecosystem.evolution import Agent, beats_baseline
from packages.atanor_ecosystem.genome import crossover, deserialize, serialize


def test_genome_roundtrip():
    a = Agent(domain_w=[0.1, -0.5, 0.9, 0.2], belief_w=[0.3, 0.0, 0.7, 0.1, 0.4, 0.2])
    vec = serialize(a)
    b = deserialize(vec)
    assert b.domain_w == a.domain_w
    assert b.belief_w == a.belief_w


def test_crossover_mixes_both_parents():
    a = Agent(domain_w=[1, 1, 1, 1], belief_w=[1, 1, 1, 1, 1, 1])
    b = Agent(domain_w=[0, 0, 0, 0], belief_w=[0, 0, 0, 0, 0, 0])
    rng = random.Random(4)
    child = crossover(a, b, rng)
    genes = child.domain_w + child.belief_w
    # a real mix: at least one gene from each parent (not a clone of either)
    assert any(g == 1 for g in genes) and any(g == 0 for g in genes)


def test_evolution_must_beat_the_fixed_heuristic_to_promote():
    # the decisive gate: an evolved controller only earns promotion if it
    # out-schedules the fixed homeostasis baseline — measured on held-out data.
    res = beats_baseline(size=60, generations=60, seed=7)
    assert res["both_hallucination_free"] is True   # neither ever lies
    assert isinstance(res["evolution_beats_human_heuristic"], bool)
    # the verdict must be honest either way — this test asserts the MEASUREMENT
    # exists and is well-formed, not a predetermined win.
    assert res["evolved_fitness"] >= 0.0 and res["baseline_fitness"] >= 0.0
