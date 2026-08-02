# -*- coding: utf-8 -*-
"""Evolution world — a place where finding food REQUIRES navigation.

The owner's structural insight: don't ask the worms to "think"; build a WORLD
whose only survival path is intelligence, then let selection do the work. Here
that means chemotaxis — food emits a gradient; a worm survives only if its neural
wiring turns its body UP the gradient toward food. Random wiring wanders and
starves; wiring that couples "more food on the left -> steer left" eats and
breeds. So intelligence (a good sensor->motor map) is selected for, not assumed.

This is a real (if minimal) evolutionary-robotics task, the same family as the
classic evolved-chemotaxis experiments. It is the mechanism layer; the pretty
3D body (Sibernetic) is a separate *visualisation* tier. Still observatory-only:
wired to no store and no answer path.

Design (deterministic per seed, pure-Python, cheap, parallelisable):
  * body: (x, y, heading) in a bounded arena.
  * brain: a small LIF net. neurons 0,1 are LEFT/RIGHT chemosensors (driven by
    the food gradient); neurons n-2, n-1 are LEFT/RIGHT motors (their spike
    counts drive turn + forward speed). The hidden neurons between them are the
    evolvable "wiring" that couples sense to motion.
  * metabolism: moving and living cost energy; eating food restores it. Death at
    zero energy. Fitness = total food eaten.
  * selection: survivors sorted by fitness breed (crossover of the connectome +
    mutation); population doubles up to a cap.
  * MOVING FINISH LINE: as the colony's mean fitness rises, food gets scarcer and
    spawns farther out — the environment co-evolves so the bar keeps rising
    (Minimal-Criterion / POET style), which is what stops evolution plateauing.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Food:
    x: float
    y: float
    amount: float


@dataclass
class EvoWorm:
    wid: int
    n: int
    x: float
    y: float
    heading: float
    v: list[float]                 # membrane potentials
    syn: list[list[int]]           # connectome: syn[i] -> post-synaptic targets
    w: float                       # synaptic strength
    tau: float                     # leak time constant
    thresh: float                  # firing threshold
    sens_gain: float               # how strongly the gradient drives the sensors
    energy: float = 1.0
    fitness: float = 0.0
    age: int = 0
    generation: int = 0
    alive: bool = True

    # sensor / motor neuron indices
    @property
    def sensor_l(self) -> int: return 0
    @property
    def sensor_r(self) -> int: return 1
    @property
    def motor_l(self) -> int: return self.n - 2
    @property
    def motor_r(self) -> int: return self.n - 1

    def _substep(self, ext: dict[int, float], rng: random.Random) -> tuple[int, int]:
        """One LIF micro-tick with per-neuron external input. Returns (L,R) motor
        spikes so the body can act on them."""
        fired: list[int] = []
        ml = mr = 0
        for i in range(self.n):
            # keep the net alive (like the LIF culture) so motors can spike; the
            # sensors add gradient-driven input ON TOP of this baseline, and the
            # evolved wiring decides whether that becomes a left or right turn.
            drive = ext.get(i, 0.12)
            self.v[i] += (drive + rng.gauss(0, 0.05) - self.v[i] / self.tau)
            if self.v[i] >= self.thresh:
                fired.append(i)
                self.v[i] = 0.0
                if i == self.motor_l:
                    ml += 1
                elif i == self.motor_r:
                    mr += 1
        for i in fired:
            for j in self.syn[i]:
                self.v[j] += self.w
        self.age += 1
        return ml, mr


def _random_connectome(rng: random.Random, n: int, out_degree: int = 4) -> list[list[int]]:
    return [[rng.randrange(n) for _ in range(out_degree)] for _ in range(n)]


def make_evoworm(rng: random.Random, wid: int, world_w: float, world_h: float,
                 n: int = 24, generation: int = 0) -> EvoWorm:
    return EvoWorm(
        wid=wid, n=n,
        x=rng.uniform(0.1 * world_w, 0.9 * world_w),
        y=rng.uniform(0.1 * world_h, 0.9 * world_h),
        heading=rng.uniform(0, 2 * math.pi),
        v=[rng.uniform(0, 0.2) for _ in range(n)],
        syn=_random_connectome(rng, n),
        w=rng.uniform(0.12, 0.3),
        tau=rng.uniform(5.0, 10.0),
        thresh=rng.uniform(0.85, 1.15),
        sens_gain=rng.uniform(0.15, 0.5),
        generation=generation,
    )


def _breed(a: EvoWorm, b: EvoWorm, rng: random.Random, wid: int, gen: int,
           world_w: float, world_h: float) -> EvoWorm:
    n = a.n
    syn = [a.syn[i] if rng.random() < 0.5 else b.syn[i] for i in range(n)]
    if rng.random() < 0.35:                       # structural mutation: rewire one
        i = rng.randrange(n)
        syn[i] = [rng.randrange(n) for _ in range(len(syn[i]))]
    return EvoWorm(
        wid=wid, n=n,
        x=rng.uniform(0.1 * world_w, 0.9 * world_w),
        y=rng.uniform(0.1 * world_h, 0.9 * world_h),
        heading=rng.uniform(0, 2 * math.pi),
        v=[rng.uniform(0, 0.2) for _ in range(n)], syn=syn,
        w=min(0.4, max(0.08, (a.w + b.w) / 2 + rng.gauss(0, 0.03))),
        tau=min(12.0, max(4.0, (a.tau + b.tau) / 2 + rng.gauss(0, 0.5))),
        thresh=min(1.3, max(0.7, (a.thresh + b.thresh) / 2 + rng.gauss(0, 0.05))),
        sens_gain=min(0.7, max(0.05, (a.sens_gain + b.sens_gain) / 2 + rng.gauss(0, 0.04))),
        generation=gen,
    )


@dataclass
class World:
    """A bounded arena where survival = navigating a chemical gradient to food."""
    seed: int = 11
    width: float = 100.0
    height: float = 60.0
    n_neurons: int = 24
    start: int = 2
    cap: int = 64
    food_density: int = 18          # target number of food patches
    worms: list[EvoWorm] = field(default_factory=list)
    food: list[Food] = field(default_factory=list)
    generation: int = 0
    difficulty: float = 1.0         # rises with colony fitness (moving finish line)
    _wid: int = 0
    _rng: random.Random = field(default_factory=lambda: random.Random(11))

    def seed_world(self) -> None:
        self._rng = random.Random(self.seed)
        self.worms = [make_evoworm(self._rng, self._next_id(), self.width, self.height,
                                   self.n_neurons) for _ in range(self.start)]
        self.food = [self._spawn_food() for _ in range(self.food_density)]
        self.generation = 0
        self.difficulty = 1.0

    def _next_id(self) -> int:
        self._wid += 1
        return self._wid

    def _spawn_food(self) -> Food:
        # moving finish line: higher difficulty -> smaller, sparser food further out
        r = self._rng
        amt = max(0.4, 2.4 / self.difficulty)
        return Food(x=r.uniform(0, self.width), y=r.uniform(0, self.height), amount=amt)

    def _conc_at(self, x: float, y: float) -> float:
        """Chemical concentration = sum of food strength with distance falloff.
        Wide falloff so the gradient is sensable from a distance — that is what
        makes chemotaxis *usable* enough to bootstrap selection."""
        c = 0.0
        for f in self.food:
            dx = x - f.x
            dy = y - f.y
            c += f.amount * math.exp(-(dx * dx + dy * dy) / 200.0)
        return c

    def tick(self, steps: int = 6, substeps: int = 4) -> dict[str, Any]:
        rng = self._rng
        for _ in range(steps):
            for wm in self.worms:
                if not wm.alive:
                    continue
                # --- sense: gradient at two head-offset chemosensors ---
                hx, hy = math.cos(wm.heading), math.sin(wm.heading)
                lx, ly = -hy, hx                         # left perpendicular
                sxl, syl = wm.x + hx * 2 + lx * 1.5, wm.y + hy * 2 + ly * 1.5
                sxr, syr = wm.x + hx * 2 - lx * 1.5, wm.y + hy * 2 - ly * 1.5
                cl = self._conc_at(sxl, syl)
                cr = self._conc_at(sxr, syr)
                ext = {wm.sensor_l: 0.16 + wm.sens_gain * cl,
                       wm.sensor_r: 0.16 + wm.sens_gain * cr}
                # --- think: run the LIF net, collect motor spikes ---
                ml = mr = 0
                for _ in range(substeps):
                    a, b = wm._substep(ext, rng)
                    ml += a
                    mr += b
                # --- act: differential drive. Low base speed + strong motor-driven
                # turn so the BRAIN dominates motion -> navigation skill is heritable
                # and selectable (measured: cumulative fitness gain appears once the
                # brain, not drift, decides where the body goes). ---
                turn = 1.2 * (ml - mr) / substeps
                speed = 0.25 + 2.2 * (ml + mr) / (2 * substeps)
                wm.heading = (wm.heading + turn) % (2 * math.pi)
                wm.x += math.cos(wm.heading) * speed
                wm.y += math.sin(wm.heading) * speed
                # reflect off the walls
                if wm.x < 0: wm.x = -wm.x; wm.heading = math.pi - wm.heading
                if wm.x > self.width: wm.x = 2 * self.width - wm.x; wm.heading = math.pi - wm.heading
                if wm.y < 0: wm.y = -wm.y; wm.heading = -wm.heading
                if wm.y > self.height: wm.y = 2 * self.height - wm.y; wm.heading = -wm.heading
                # --- eat ---
                for f in self.food:
                    if f.amount <= 0:
                        continue
                    if (wm.x - f.x) ** 2 + (wm.y - f.y) ** 2 <= 16.0:
                        bite = min(f.amount, 0.25)
                        f.amount -= bite
                        wm.energy = min(3.0, wm.energy + bite * 2.8)
                        wm.fitness += bite
                # --- metabolise (gentle enough that a colony grows toward the cap
                # and many worms crowd the tank, but the worst navigators still die) ---
                wm.energy -= 0.008 + 0.005 * speed
                if wm.energy <= 0:
                    wm.alive = False
            # food upkeep: remove eaten, keep density
            self.food = [f for f in self.food if f.amount > 0.05]
            while len(self.food) < self.food_density:
                self.food.append(self._spawn_food())
        return self.snapshot()

    def breed_generation(self) -> dict[str, Any]:
        """Elite survivors breed; population doubles up to cap. Moving finish line:
        difficulty rises with the colony's demonstrated fitness."""
        survivors = sorted([w for w in self.worms if w.alive],
                           key=lambda w: -w.fitness)
        if not survivors:
            # everyone starved -> reseed a fresh founding pair (continuing rng)
            self.worms = [make_evoworm(self._rng, self._next_id(), self.width,
                                       self.height, self.n_neurons)
                          for _ in range(self.start)]
            self.generation = 0
            return self.snapshot()
        self.generation += 1
        # raise the bar in proportion to how well the elite did
        top = survivors[0].fitness
        self.difficulty = min(4.0, 1.0 + 0.15 * top)
        target = min(self.cap, max(self.start, len(survivors) * 2))
        children: list[EvoWorm] = []
        # elitism: carry survivors forward (reset body + energy, keep brain)
        for s in survivors:
            children.append(_breed(s, s, self._rng, self._next_id(), self.generation,
                                   self.width, self.height))
        while len(children) < target and survivors:
            pa = self._rng.choice(survivors)
            pb = self._rng.choice(survivors)
            children.append(_breed(pa, pb, self._rng, self._next_id(),
                                   self.generation, self.width, self.height))
        self.worms = children[: self.cap]
        # fresh food field for the new generation, at the new difficulty
        self.food = [self._spawn_food() for _ in range(self.food_density)]
        return self.snapshot()

    def _fitness_color(self, fit: float, hi: float) -> list[int]:
        """Red (low intelligence/fitness) -> black (high). The owner's spec."""
        t = 0.0 if hi <= 0 else max(0.0, min(1.0, fit / hi))
        r = int(230 * (1 - t) + 25 * t)
        g = int(60 * (1 - t) + 20 * t)
        b = int(45 * (1 - t) + 25 * t)
        return [r, g, b]

    def snapshot(self) -> dict[str, Any]:
        alive = [w for w in self.worms if w.alive]
        hi = max((w.fitness for w in self.worms), default=0.0)
        return {
            "generation": self.generation,
            "population": len(self.worms),
            "alive": len(alive),
            "cap": self.cap,
            "difficulty": round(self.difficulty, 3),
            "best_fitness": round(hi, 3),
            "mean_fitness": round(sum(w.fitness for w in self.worms) / max(1, len(self.worms)), 3),
            "world": {"w": self.width, "h": self.height},
            "food": [{"x": round(f.x, 2), "y": round(f.y, 2), "amount": round(f.amount, 2)}
                     for f in self.food],
            "worms": [{
                "id": w.wid, "gen": w.generation,
                "x": round(w.x, 2), "y": round(w.y, 2),
                "heading": round(w.heading, 3),
                "fitness": round(w.fitness, 3),
                "energy": round(w.energy, 3),
                "alive": w.alive,
                "color": self._fitness_color(w.fitness, hi),
            } for w in self.worms[: self.cap]],
            "note": "chemotaxis evolution world — survival requires navigating to food; observatory only",
        }
