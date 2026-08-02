# -*- coding: utf-8 -*-
"""Digital genome — the serialized 'DNA' of an ecosystem agent.

The owner's reverse-engineering step 1: encode a policy as a compact, fast-to-
copy vector so millions of copies mutate/cross at C-speed. Honest scope: this is
a genome for a META-CONTROLLER policy (resource scheduling + belief caution),
NOT a neural substrate that grows language. Growing the vector grows scheduling
capacity, not grammar — the selection task contains no language pressure.

Layout (a flat float vector, the 'digital DNA'):
  [ domain_w (n_domains) | belief_w (n_beliefs) ]
Crossover = uniform gene mix of two parents (sexual reproduction). Mutation =
gaussian jitter. Both are pure and deterministic under a seeded RNG.
"""
from __future__ import annotations

import random

from .evolution import Agent


def serialize(agent: Agent) -> list[float]:
    """Agent -> flat DNA vector."""
    return [len(agent.domain_w)] + list(agent.domain_w) + list(agent.belief_w)


def deserialize(vec: list[float], origin: str = "genome") -> Agent:
    """DNA vector -> Agent (inverse of serialize)."""
    n_dom = int(round(vec[0]))
    dom = list(vec[1:1 + n_dom])
    bel = [min(1.0, max(0.0, w)) for w in vec[1 + n_dom:]]
    return Agent(domain_w=dom, belief_w=bel, origin=origin)


def crossover(a: Agent, b: Agent, rng: random.Random, *, gen: int = 0) -> Agent:
    """Super-crossover (uniform sexual recombination): each gene is inherited
    from parent a or b at 50/50. The two parents must share genome length."""
    dom = [a.domain_w[i] if rng.random() < 0.5 else b.domain_w[i]
           for i in range(min(len(a.domain_w), len(b.domain_w)))]
    bel = [a.belief_w[i] if rng.random() < 0.5 else b.belief_w[i]
           for i in range(min(len(a.belief_w), len(b.belief_w)))]
    return Agent(domain_w=dom, belief_w=bel, born_gen=gen,
                 origin=f"{a.origin}x{b.origin}" if a.origin != b.origin else a.origin)
