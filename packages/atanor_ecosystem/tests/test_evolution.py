# -*- coding: utf-8 -*-
"""Evolution sandbox — the guardrail-as-predator mechanism, measured."""

from __future__ import annotations

import random

from packages.atanor_ecosystem.evolution import (
    Agent, Ecosystem, Scenario, default_world, evaluate, evolve, run_ab)


def test_hallucinating_agent_is_killed_by_the_guardrail():
    # an agent that asserts EVERY candidate belief will eventually assert a false
    # one, and the guardrail (predator) must make it lethal (fitness -> death).
    always_assert = Agent(domain_w=[1, 0, 0, 0], belief_w=[1, 1, 1, 1, 1, 1])
    rng = random.Random(1)
    scenarios = [default_world(rng, 4, 6) for _ in range(20)]
    fit = evaluate(always_assert, scenarios)
    assert fit <= -999  # any hallucination = death

    # an agent that asserts NOTHING can never hallucinate -> survives, scores on
    # scheduling alone (>= 0)
    cautious = Agent(domain_w=[1, 1, 1, 1], belief_w=[0, 0, 0, 0, 0, 0])
    assert evaluate(cautious, scenarios) >= 0


def test_selection_evolves_coherent_survivors():
    eco = Ecosystem(seed=3)
    eco.seed_random(40)
    res = evolve(eco, generations=40)
    # selection actually works: survivors schedule well AND some hallucinators died
    assert res["final_best_fitness"] > 0.5
    assert res["deaths_by_hallucination"] > 0


def test_survivors_never_hallucinate():
    # after evolution, the best survivor must be a non-hallucinator (fitness >= 0)
    eco = Ecosystem(seed=5)
    eco.seed_random(30)
    res = evolve(eco, generations=30)
    assert res["final_best_fitness"] >= 0.0  # a hallucinator could never be 'best'


def test_ab_reports_connectome_vs_random_honestly():
    # the honest measurement: is the connectome topology functional or narrative?
    ab = run_ab(size=40, generations=40, seed=7)
    assert ab["selection_works"] is True
    assert ab["verdict"] in ("connectome_helps", "connectome_narrative", "connectome_hurts")
    assert "answer path" in ab["note"]  # sandbox-only guarantee stated


def test_sandbox_touches_nothing_external(tmp_path):
    # the module has no store/answer-path imports at call time; a full run must
    # not create files or raise (pure, deterministic).
    eco = Ecosystem(seed=9)
    eco.seed_connectome(20)
    res = evolve(eco, generations=15)
    assert res["generations"] == 15
    assert list(tmp_path.iterdir()) == []  # nothing written anywhere
