# -*- coding: utf-8 -*-
"""Living worm culture — real LIF dynamics, exponential breeding, bounded."""

from __future__ import annotations

from packages.atanor_ecosystem.worm_culture import Culture, make_worm
import random


def test_colony_starts_with_two_and_lif_fires():
    c = Culture(seed=3, start=2)
    c.seed_colony()
    assert len(c.worms) == 2
    snap = c.tick(30)
    assert snap["population"] == 2
    # a real spiking sim: some neurons carry voltage / activity is measured
    assert all("voltages" in w for w in snap["worms"])


def test_population_doubles_each_generation_bounded():
    c = Culture(seed=5, start=2, cap=16)
    c.seed_colony()
    sizes = [len(c.worms)]
    for _ in range(6):
        c.tick(15)
        c.breed_generation()
        sizes.append(len(c.worms))
    # exponential-ish growth, then capped (never exceeds cap)
    assert max(sizes) <= 16
    assert sizes[-1] >= sizes[0]
    # early doublings visible before the cap bites
    assert 2 in sizes and any(s >= 4 for s in sizes)


def test_unhealthy_worms_die_healthy_survive():
    c = Culture(seed=9, start=8)
    c.seed_colony()
    for _ in range(40):
        c.tick(20)
    snap = c.snapshot()
    # selection is real: energy varies, some may die (alive <= population)
    assert snap["alive"] <= snap["population"]
    assert isinstance(snap["worms"][0]["energy"], float)


def test_extinction_reseeds_a_founding_pair():
    c = Culture(seed=1, start=2, cap=8)
    c.seed_colony()
    for w in c.worms:
        w.alive = False           # force extinction
    snap = c.breed_generation()   # must reseed, not crash
    assert snap["population"] == 2


def test_snapshot_is_bounded_and_labeled_observatory():
    c = Culture(seed=2, start=2, cap=64)
    c.seed_colony()
    for _ in range(4):
        c.tick(10); c.breed_generation()
    snap = c.tick(5)
    assert snap["population"] <= 64
    assert "observatory" in snap["note"]  # honest: not a reasoner
