# -*- coding: utf-8 -*-
"""Living worm culture — a REAL spiking-neuron colony you can watch.

Honest scope (say it plainly): this is an AQUARIUM / OBSERVATORY, not a reasoner.
It runs a genuine leaky-integrate-and-fire (LIF) neural simulation of small
connectomes, bred by selection, on ONE core, bounded — so the owner can literally
watch living organisms pulse and reproduce. It makes NO intelligence claim and is
wired to NOTHING (no store, no answer path). It is the embodiment/observability
layer the OEE verdict said was the defensible use of the connectome idea.

Real dynamics (not decoration):
  * each worm has N LIF neurons: v += (input - v/tau) dt; spike when v>=thresh,
    then reset. Synapses propagate spikes along a small random connectome.
  * metabolism: a worm spends energy per tick, earns energy by keeping its
    network ALIVE and ACTIVE (neither silent nor seizing) — homeostatic fitness.
  * reproduction: when the colony ticks a 'generation', survivors breed (crossover
    of connectomes + mutation) and the population DOUBLES (2 -> 4 -> 8 ...) up to
    a hard cap, so it grows like real exponential breeding but stays bounded.
Deterministic per seed, pure-Python, single core, cheap.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Worm:
    wid: int
    n: int
    v: list[float]                 # membrane potentials
    syn: list[list[int]]           # connectome: syn[i] = post-synaptic targets of i
    w: float                       # synaptic strength
    tau: float                     # leak time constant
    thresh: float                  # firing threshold (self-regulates via plasticity)
    energy: float = 1.0
    age: int = 0
    generation: int = 0
    alive: bool = True
    target_rate: float = 0.2       # homeostatic set-point (fraction of neurons/tick)
    adapt: float = 0.08            # how fast the worm tunes its own threshold

    def step(self, drive: float, rng: random.Random) -> int:
        """One LIF tick. Returns the number of neurons that spiked this tick.

        Real intrinsic plasticity (firing-rate homeostasis): after each tick the
        worm nudges its own threshold toward whatever keeps it near target_rate —
        fire too much, threshold rises; fire too little, it falls. So a lineage
        self-stabilises into a healthy rhythm instead of dying silent or seizing.
        The GENETICS (tau, w, connectome, adapt speed, target) still vary and are
        selected on; plasticity only removes the lethal all-or-nothing lottery."""
        spikes = 0
        fired: list[int] = []
        for i in range(self.n):
            # leak + external drive + a little noise (sensory jitter)
            self.v[i] += (drive + rng.gauss(0, 0.06) - self.v[i] / self.tau)
            if self.v[i] >= self.thresh:
                fired.append(i)
                self.v[i] = 0.0
                spikes += 1
        # synaptic propagation of this tick's spikes
        for i in fired:
            for j in self.syn[i]:
                self.v[j] += self.w
        # intrinsic plasticity: chase the homeostatic set-point
        rate = spikes / max(1, self.n)
        self.thresh += self.adapt * (rate - self.target_rate)
        if self.thresh < 0.3:
            self.thresh = 0.3
        elif self.thresh > 2.5:
            self.thresh = 2.5
        self.age += 1
        return spikes


def _random_connectome(rng: random.Random, n: int, out_degree: int = 3) -> list[list[int]]:
    return [[rng.randrange(n) for _ in range(out_degree)] for _ in range(n)]


def make_worm(rng: random.Random, wid: int, n: int = 24, generation: int = 0) -> Worm:
    return Worm(
        wid=wid, n=n,
        v=[rng.uniform(0, 0.2) for _ in range(n)],
        syn=_random_connectome(rng, n),
        w=rng.uniform(0.12, 0.28),
        tau=rng.uniform(5.0, 10.0),
        thresh=rng.uniform(0.85, 1.15),
        generation=generation,
        target_rate=rng.uniform(0.12, 0.3),   # each lineage's preferred rhythm
        adapt=rng.uniform(0.04, 0.12),         # how fast it self-tunes
    )


def _breed(a: Worm, b: Worm, rng: random.Random, wid: int, gen: int) -> Worm:
    """Crossover two worms' connectomes + parameters, with mutation."""
    n = a.n
    syn = [a.syn[i] if rng.random() < 0.5 else b.syn[i] for i in range(n)]
    # structural mutation: occasionally rewire one synapse
    if rng.random() < 0.3:
        i = rng.randrange(n)
        syn[i] = [rng.randrange(n) for _ in range(len(syn[i]))]
    return Worm(
        wid=wid, n=n, v=[rng.uniform(0, 0.2) for _ in range(n)], syn=syn,
        # inherit parents' parameters (mean + mutation), clamped to the survivable band
        w=min(0.35, max(0.08, (a.w + b.w) / 2 + rng.gauss(0, 0.03))),
        tau=min(12.0, max(4.0, (a.tau + b.tau) / 2 + rng.gauss(0, 0.5))),
        thresh=min(1.3, max(0.7, (a.thresh + b.thresh) / 2 + rng.gauss(0, 0.05))),
        generation=gen,
        target_rate=min(0.4, max(0.08, (a.target_rate + b.target_rate) / 2 + rng.gauss(0, 0.02))),
        adapt=min(0.2, max(0.02, (a.adapt + b.adapt) / 2 + rng.gauss(0, 0.01))),
    )


@dataclass
class Culture:
    """A bounded, single-core colony that breeds and doubles."""
    seed: int = 7
    n_neurons: int = 24
    start: int = 2            # begin with two worms
    cap: int = 64            # hard population ceiling (bounded memory / 1 core)
    worms: list[Worm] = field(default_factory=list)
    generation: int = 0
    _wid: int = 0
    _rng: random.Random = field(default_factory=lambda: random.Random(7))

    def seed_colony(self) -> None:
        self._rng = random.Random(self.seed)
        self.worms = [make_worm(self._rng, self._next_id(), self.n_neurons)
                      for _ in range(self.start)]
        self.generation = 0

    def _next_id(self) -> int:
        self._wid += 1
        return self._wid

    def tick(self, ticks: int = 20) -> dict[str, Any]:
        """Advance the colony's neural dynamics for `ticks`, score homeostatic
        fitness, and return a viz snapshot. Alive = active but not seizing."""
        rng = self._rng
        for _ in range(ticks):
            drive = 0.14 + 0.03 * math.sin(self.generation * 0.3)  # gentle world rhythm
            for wm in self.worms:
                if not wm.alive:
                    continue
                s = wm.step(drive, rng)
                rate = s / max(1, wm.n)
                # homeostasis: reward a healthy firing band (~6-45%), spend energy.
                # energy is capped so healthy worms are not immortal — drift toward
                # silence or seizure still culls them, keeping selection alive.
                if 0.06 <= rate <= 0.45:
                    wm.energy = min(2.0, wm.energy + 0.015)
                else:  # silent (dead-ish) or seizing (runaway) -> costly
                    wm.energy -= 0.02
                wm.energy -= 0.004
                if wm.energy <= 0:
                    wm.alive = False
        return self.snapshot()

    def breed_generation(self) -> dict[str, Any]:
        """Survivors reproduce; population DOUBLES up to the cap (2->4->8...)."""
        survivors = sorted([w for w in self.worms if w.alive],
                           key=lambda w: -w.energy)
        if not survivors:
            # extinction -> reseed a fresh founding pair from the CONTINUING rng
            # (never re-reset the seed, or we'd recreate the same doomed worms
            # forever). A new draw gives evolution another roll of the dice.
            self.worms = [make_worm(self._rng, self._next_id(), self.n_neurons)
                          for _ in range(self.start)]
            self.generation = 0
            return self.snapshot()
        self.generation += 1
        target = min(self.cap, max(self.start, len(survivors) * 2))
        children: list[Worm] = list(survivors)
        while len(children) < target and survivors:
            pa = self._rng.choice(survivors)
            pb = self._rng.choice(survivors)
            children.append(_breed(pa, pb, self._rng, self._next_id(), self.generation))
        self.worms = children[: self.cap]
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """A viz-ready snapshot: per-worm activity + neuron voltages (for the
        SPLATRA-style live field). Bounded size."""
        alive = [w for w in self.worms if w.alive]
        return {
            "generation": self.generation,
            "population": len(self.worms),
            "alive": len(alive),
            "cap": self.cap,
            "worms": [{
                "id": w.wid, "gen": w.generation,
                "energy": round(w.energy, 3),
                "activity": round(sum(1 for x in w.v if x > 0.4) / max(1, w.n), 3),
                "voltages": [round(x, 3) for x in w.v[:24]],
            } for w in self.worms[:self.cap]],
            "note": "living LIF colony — observatory only, not wired to any reasoning",
        }
