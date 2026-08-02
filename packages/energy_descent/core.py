"""Energy-descent settling — the 'gravity' hypothesis, applied where it is TRUE here.

Owner-supplied hypothesis (2026-07-06): give reasoning an energy LANDSCAPE instead of an
unconstrained next-step map; thought then rolls downhill (gradient flow of a scalar), a
conservative field has no limit cycles, and the energy acts as a Lyapunov function — so
looping is impossible and settling is guaranteed.

VERIFIED — what the math honestly buys OUR (graph, No-LLM) engine:
  * a traversal step is accepted ONLY if it STRICTLY lowers a bounded-below scalar
    energy over a finite state set → the visited energies form a strictly decreasing
    real sequence → no state can ever recur (a revisit would need an equal-or-lower
    energy that was already consumed) → cycles are impossible BY CONSTRUCTION and
    termination needs no arbitrary round cap (discrete Lyapunov argument);
  * logic as slope: encoding P⇒Q as E(Q) < E(P) makes valid inference literally the
    downhill direction, so chains follow entailment instead of wandering.

HONEST LIMITS — what it does NOT buy:
  * it cannot make a wrong graph true: the landscape's shape comes from real relation
    confidence/grounding, and garbage relations still settle — at a garbage minimum;
  * our answers are not a recurrent net's trajectory, so the LLM-hallucination framing
    translates here ONLY as: multi-hop traversal cannot wander or loop, and must stop
    at the best-grounded reachable conclusion or surface a local minimum as an honest
    abstention ("no downhill step from here").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Hashable

State = Hashable


@dataclass(frozen=True)
class SettleStep:
    state: State
    energy: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "energy": self.energy, "reason": self.reason}


@dataclass
class SettleResult:
    settled_state: State
    settled_energy: float
    path: list[SettleStep] = field(default_factory=list)
    local_minimum: bool = False          # True → no downhill neighbour existed (honest stop)
    steps_taken: int = 0

    @property
    def energy_trace(self) -> list[float]:
        return [s.energy for s in self.path]

    def to_dict(self) -> dict[str, Any]:
        return {
            "settled_state": self.settled_state,
            "settled_energy": self.settled_energy,
            "path": [s.to_dict() for s in self.path],
            "local_minimum": self.local_minimum,
            "steps_taken": self.steps_taken,
            "energy_trace": self.energy_trace,
        }


class EnergyDescent:
    """Strict-descent settling over a finite neighbour graph.

    energy_fn(state) -> float            bounded-below scalar (the landscape)
    neighbors_fn(state) -> iterable      candidate next states (edges from the real graph)

    settle() always terminates: each accepted step strictly lowers the energy, and a
    finite state set admits only finitely many strictly-decreasing values. There is no
    max_rounds knob to tune — termination is structural, not configured. max_states is
    a defensive bound on ill-behaved neighbour generators only; hitting it raises.
    """

    def __init__(self, energy_fn: Callable[[State], float],
                 neighbors_fn: Callable[[State], Any], *, max_states: int = 100_000) -> None:
        self._energy = energy_fn
        self._neighbors = neighbors_fn
        self._max_states = int(max_states)

    def settle(self, start: State) -> SettleResult:
        current = start
        e_curr = float(self._energy(current))
        path = [SettleStep(current, e_curr, "start")]
        visited = 1
        while True:
            best: State | None = None
            e_best = e_curr
            for cand in self._neighbors(current):
                visited += 1
                if visited > self._max_states:
                    raise RuntimeError("energy_descent: neighbour generator exceeded max_states")
                e_cand = float(self._energy(cand))
                if e_cand < e_best:      # STRICT decrease only — the Lyapunov condition
                    best, e_best = cand, e_cand
            if best is None:
                return SettleResult(settled_state=current, settled_energy=e_curr, path=path,
                                    local_minimum=len(path) == 1, steps_taken=len(path) - 1)
            current, e_curr = best, e_best
            path.append(SettleStep(current, e_curr,
                                   f"downhill ({path[-1].energy:.4f} → {e_curr:.4f})"))
