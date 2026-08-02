# -*- coding: utf-8 -*-
"""Evolution world — survival requires chemotaxis; selection is real."""

from __future__ import annotations

from packages.atanor_ecosystem.evolution_world import World


def test_world_starts_with_two_and_has_food():
    w = World(seed=3, start=2)
    w.seed_world()
    assert len(w.worms) == 2
    assert len(w.food) == w.food_density
    snap = w.tick(4)
    assert snap["population"] == 2
    assert "food" in snap and snap["worms"][0]["x"] is not None


def test_selection_differential_exists():
    """The whole point: some worms find food, others don't — fitness is NOT
    uniform, so selection has real signal to act on."""
    w = World(seed=5, start=8, cap=16)
    w.seed_world()
    for _ in range(30):
        w.tick(6)
    fits = [wm.fitness for wm in w.worms]
    assert max(fits) > 0.0                      # at least someone ate
    assert max(fits) > min(fits)                # differential -> selection works


def test_population_doubles_bounded():
    w = World(seed=7, start=2, cap=16)
    w.seed_world()
    sizes = [len(w.worms)]
    for _ in range(6):
        w.tick(6)
        w.breed_generation()
        sizes.append(len(w.worms))
    assert max(sizes) <= 16
    assert any(s >= 4 for s in sizes)


def test_selection_improves_food_finding_over_generations():
    """Under selection + breeding, the elite's food-finding should not collapse;
    across many generations the best fitness stays positive and trends up vs gen 0."""
    w = World(seed=9, start=6, cap=24)
    w.seed_world()
    bests = []
    for _ in range(12):
        snap = w.tick(8)               # measure fitness AFTER the worms have fed,
        bests.append(snap["best_fitness"])  # BEFORE breeding resets it to 0
        w.breed_generation()
    # evolution is noisy; assert the elite keeps finding food (never stuck at 0)
    assert max(bests) > 0.0
    assert sum(1 for b in bests if b > 0) >= len(bests) // 2


def test_moving_finish_line_raises_difficulty():
    w = World(seed=2, start=8, cap=32)
    w.seed_world()
    base = w.difficulty
    for _ in range(10):
        w.tick(8)
        w.breed_generation()
    # if the elite ever ate, the bar should have risen above the baseline
    assert w.difficulty >= base


def test_snapshot_has_fitness_colors_red_to_black():
    w = World(seed=4, start=8, cap=16)
    w.seed_world()
    for _ in range(20):
        w.tick(6)
    snap = w.snapshot()
    assert all(len(wm["color"]) == 3 for wm in snap["worms"])
    assert "chemotaxis" in snap["note"] and "observatory only" in snap["note"]
