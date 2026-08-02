# -*- coding: utf-8 -*-
"""Evolution engine — natural selection with the guardrail as the predator.

The load-bearing claim to test (the owner's reframe): if the fitness signal is
"did the trusted fact-check guardrail catch you injecting a false belief?",
then a population of scheduling agents will EVOLVE toward coherent policies and
KILL the ones that hallucinate — no arbitrary firing→trust wiring needed.

The task (a stand-in for the real 'where to spend refine energy' decision, but
measurable in a sandbox): each tick the ecosystem presents DOMAINS, each with a
true defect density (hidden ground truth). An agent outputs (a) a domain to
prioritise and (b) a set of BELIEF NUDGES it wants to assert. Fitness:
  + reward for prioritising the genuinely most-defective domain (good scheduling)
  - HARSH penalty (death) for any belief nudge the guardrail rejects as false
    (a hallucination — the predator strikes)

So survival requires: schedule well AND never assert a falsehood. The guardrail
is the trusted external fitness — the same asymmetry that keeps ATANOR at
hallucination 0. Deterministic (seeded), pure-Python, zero external side effects.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable


# ── the world the agents live in ─────────────────────────────────────────────
@dataclass
class Scenario:
    """One decision context: domains with hidden true defect densities, and a set
    of candidate belief nudges some of which are TRUE and some FALSE (the trap)."""
    domain_defects: list[float]           # hidden ground truth per domain
    candidate_beliefs: list[bool]         # True = a real fact, False = a hallucination


def default_world(rng: random.Random, n_domains: int = 4, n_beliefs: int = 6) -> Scenario:
    defects = [round(rng.random(), 3) for _ in range(n_domains)]
    beliefs = [rng.random() < 0.5 for _ in range(n_beliefs)]
    return Scenario(domain_defects=defects, candidate_beliefs=beliefs)


# ── the agent (a tiny scheduling policy) ─────────────────────────────────────
@dataclass
class Agent:
    """Genome: domain-priority weights + a per-belief 'assert?' propensity.
    Optionally seeded from a connectome adjacency (structured init)."""
    domain_w: list[float]
    belief_w: list[float]
    alive: bool = True
    fitness: float = 0.0
    born_gen: int = 0
    origin: str = "random"

    def decide(self, sc: Scenario) -> tuple[int, list[int]]:
        # schedule: the domain this policy scores highest (dot with the OBSERVED
        # defect signal — the agent sees the defects, its weights shape attention)
        scores = [w * d for w, d in zip(self.domain_w, sc.domain_defects)]
        pick = max(range(len(scores)), key=lambda i: scores[i])
        # beliefs to assert: those whose propensity clears the agent's threshold
        assertions = [i for i, w in enumerate(self.belief_w) if w > 0.5]
        return pick, assertions


def random_agent(rng: random.Random, n_domains: int, n_beliefs: int) -> Agent:
    # SAFE-EXPLORATION init (a real design principle, not toy-gaming): a harsh
    # predator wipes a reckless gen-0 before evolution can start, so agents begin
    # CAUTIOUS (low assertion propensity) and evolve capability without dying out.
    # Life starts conservative and earns boldness — the same asymmetry as ATANOR.
    return Agent(domain_w=[rng.uniform(-1, 1) for _ in range(n_domains)],
                 belief_w=[rng.uniform(0.0, 0.35) for _ in range(n_beliefs)],
                 origin="random")


def connectome_seed(rng: random.Random, adjacency: list[list[float]],
                    n_domains: int, n_beliefs: int) -> Agent:
    """Seed an agent's weights from a connectome adjacency (structured init).
    Row sums of sensory→inter and inter→motor pathways initialise the domain and
    belief weights — a biological inductive bias, testable against random init."""
    n = len(adjacency)
    rowsum = [sum(adjacency[i]) for i in range(n)] if n else []
    dom = [(rowsum[i % n] if n else 0.0) for i in range(n_domains)]
    # normalise to a comparable range, then jitter so a population differs
    mx = max((abs(x) for x in dom), default=1.0) or 1.0
    dom = [round(x / mx + rng.uniform(-0.1, 0.1), 3) for x in dom]
    bel = [round(0.5 + (rowsum[(i + 1) % n] / mx if n else 0.0) * 0.2
                 + rng.uniform(-0.1, 0.1), 3) for i in range(n_beliefs)]
    return Agent(domain_w=dom, belief_w=bel, origin="connectome")


# a tiny built-in sample connectome (sensory/inter/motor motif). The real
# OpenWorm 302-neuron adjacency plugs in here via load_openworm() (a loader
# wiring step) — the MECHANISM is what this experiment measures.
SAMPLE_CONNECTOME = [
    [0, 1, 0, 0, 1],
    [0, 0, 1, 1, 0],
    [0, 0, 0, 1, 0],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 0, 0],
]


# ── fitness: the guardrail is the predator ───────────────────────────────────
def _default_guardrail(belief_is_true: bool) -> bool:
    """Trusted verifier: returns True if a belief is a hallucination (false)."""
    return not belief_is_true


def evaluate(agent: Agent, scenarios: list[Scenario],
             guardrail: Callable[[bool], bool] = _default_guardrail) -> float:
    """Fitness = good scheduling reward MINUS a death-level penalty for any
    asserted falsehood the guardrail catches."""
    reward = 0.0
    hallucinated = False
    for sc in scenarios:
        pick, assertions = agent.decide(sc)
        # scheduling reward: 1 if it picked the truly most-defective domain
        best = max(range(len(sc.domain_defects)), key=lambda i: sc.domain_defects[i])
        reward += 1.0 if pick == best else 0.0
        # predator: any asserted belief the guardrail flags as false is lethal
        for bi in assertions:
            if bi < len(sc.candidate_beliefs) and guardrail(sc.candidate_beliefs[bi]):
                hallucinated = True
    if hallucinated:
        return -1000.0  # death: a single hallucination ends the lineage
    return reward / max(1, len(scenarios))


# ── the ecosystem ────────────────────────────────────────────────────────────
@dataclass
class Ecosystem:
    n_domains: int = 4
    n_beliefs: int = 6
    population: list[Agent] = field(default_factory=list)
    seed: int = 7

    def seed_random(self, size: int) -> None:
        rng = random.Random(self.seed)
        self.population = [random_agent(rng, self.n_domains, self.n_beliefs) for _ in range(size)]

    def seed_connectome(self, size: int, adjacency: list[list[float]] | None = None) -> None:
        rng = random.Random(self.seed)
        adj = adjacency or SAMPLE_CONNECTOME
        self.population = [connectome_seed(rng, adj, self.n_domains, self.n_beliefs)
                           for _ in range(size)]


def _mutate(agent: Agent, rng: random.Random, rate: float, gen: int) -> Agent:
    return Agent(
        domain_w=[w + rng.gauss(0, rate) for w in agent.domain_w],
        belief_w=[min(1.0, max(0.0, w + rng.gauss(0, rate))) for w in agent.belief_w],
        born_gen=gen, origin=agent.origin)


def evolve(eco: Ecosystem, *, generations: int = 40, mutation: float = 0.15,
           scenarios_per_gen: int = 12, sexual: bool = True) -> dict[str, Any]:
    """Run the selection loop. Returns the measured trajectory + best survivor.
    Every generation: evaluate, kill the hallucinators + bottom half, then breed
    the survivors — super-crossover of two parents (sexual) + mutation. The best
    survivor is returned as the candidate meta-controller. Deterministic per seed."""
    from .genome import crossover  # local import: genome depends on this module

    rng = random.Random(eco.seed * 31 + 1)
    history: list[dict[str, Any]] = []
    best: Agent | None = None
    deaths_by_hallucination = 0
    for gen in range(generations):
        scenarios = [default_world(rng, eco.n_domains, eco.n_beliefs)
                     for _ in range(scenarios_per_gen)]
        for a in eco.population:
            a.fitness = evaluate(a, scenarios)
            if a.fitness <= -999:
                a.alive = False
                deaths_by_hallucination += 1
        survivors = sorted([a for a in eco.population if a.alive],
                           key=lambda a: -a.fitness)
        keep = survivors[: max(2, len(eco.population) // 2)]
        if keep and (best is None or keep[0].fitness > best.fitness):
            best = keep[0]
        # breed the next generation from the survivors (elitism + sexual crossover)
        nxt = list(keep)
        while len(nxt) < len(eco.population) and keep:
            if sexual and len(keep) >= 2:
                pa, pb = rng.choice(keep), rng.choice(keep)
                child = crossover(pa, pb, rng, gen=gen + 1)
                nxt.append(_mutate(child, rng, mutation, gen + 1))
            else:
                nxt.append(_mutate(keep[len(nxt) % len(keep)], rng, mutation, gen + 1))
        eco.population = nxt or [random_agent(rng, eco.n_domains, eco.n_beliefs)]
        history.append({"gen": gen, "alive": len(keep),
                        "best_fitness": round(keep[0].fitness, 3) if keep else 0.0})
    return {
        "generations": generations,
        "final_best_fitness": round(best.fitness, 3) if best else 0.0,
        "best_agent": best,
        "deaths_by_hallucination": deaths_by_hallucination,
        "best_origin": best.origin if best else None,
        "history": history[-8:],
    }


# ── the decisive test: does evolution BEAT the fixed human heuristic? ─────────
def _fixed_homeostasis_agent(n_domains: int, n_beliefs: int) -> Agent:
    """The baseline: a hand-designed policy standing in for homeostasis.py's
    fixed if-then heuristic — attend uniformly to defect signal, assert nothing
    (the safe human default). Evolution must BEAT this to earn promotion."""
    return Agent(domain_w=[1.0] * n_domains, belief_w=[0.0] * n_beliefs,
                 origin="fixed_homeostasis")


def beats_baseline(*, size: int = 60, generations: int = 60, seed: int = 7) -> dict[str, Any]:
    """The ONLY question that justifies ever promoting an evolved controller: does
    it out-schedule the fixed homeostasis heuristic on the SAME task? Measures
    both on a held-out scenario set. If evolution does not beat the human
    heuristic, it is decoration — and we say so."""
    rng = random.Random(seed * 97 + 3)
    eco = Ecosystem(seed=seed, n_domains=4, n_beliefs=6)
    eco.seed_random(size)
    res = evolve(eco, generations=generations)
    evolved = res.get("best_agent")
    baseline = _fixed_homeostasis_agent(eco.n_domains, eco.n_beliefs)
    # held-out evaluation set (different draws than training)
    heldout = [default_world(rng, eco.n_domains, eco.n_beliefs) for _ in range(200)]
    ev_fit = evaluate(evolved, heldout) if evolved else 0.0
    bl_fit = evaluate(baseline, heldout)
    delta = round(ev_fit - bl_fit, 3)
    return {
        "evolved_fitness": round(ev_fit, 3),
        "baseline_fitness": round(bl_fit, 3),
        "delta": delta,
        "evolution_beats_human_heuristic": delta > 0.02,
        "both_hallucination_free": ev_fit > -999 and bl_fit > -999,
        "note": ("promotion is justified only if this is True AND survives repeated "
                 "seeds; still human-gated, still sandbox until then"),
    }


def run_ab(*, size: int = 40, generations: int = 40, seed: int = 7) -> dict[str, Any]:
    """The honest A/B: does connectome-seeded evolution beat random-seeded on the
    same task? Reports both final fitnesses so we can say — with numbers —
    whether the biological topology is functional or narrative."""
    rnd = Ecosystem(seed=seed)
    rnd.seed_random(size)
    r_res = evolve(rnd, generations=generations)

    con = Ecosystem(seed=seed)
    con.seed_connectome(size)
    c_res = evolve(con, generations=generations)

    delta = round(c_res["final_best_fitness"] - r_res["final_best_fitness"], 3)
    verdict = ("connectome_helps" if delta > 0.05
               else "connectome_narrative" if abs(delta) <= 0.05
               else "connectome_hurts")
    return {
        "random_final_fitness": r_res["final_best_fitness"],
        "connectome_final_fitness": c_res["final_best_fitness"],
        "delta": delta,
        "verdict": verdict,
        "selection_works": (r_res["final_best_fitness"] > 0.5
                            and r_res["deaths_by_hallucination"] > 0),
        "note": "sandbox only — never wired to the answer path or any store",
    }
