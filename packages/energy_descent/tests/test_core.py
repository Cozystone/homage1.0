"""The Lyapunov claims must hold as TESTS, not prose: strict decrease, cycle
impossibility, cap-free termination, logic-as-slope, and honest local-minimum stops."""
from __future__ import annotations

import pytest

from packages.energy_descent import EnergyDescent


def _descender(graph: dict, energies: dict) -> EnergyDescent:
    return EnergyDescent(lambda s: energies[s], lambda s: graph.get(s, []))


def test_settles_at_global_bottom_and_trace_strictly_decreases():
    graph = {"P": ["Q", "R"], "Q": ["S"], "R": [], "S": []}
    energies = {"P": 3.0, "Q": 2.0, "R": 2.5, "S": 1.0}
    res = _descender(graph, energies).settle("P")
    assert res.settled_state == "S"
    trace = res.energy_trace
    assert all(a > b for a, b in zip(trace, trace[1:]))   # strictly decreasing, every step


def test_cycle_cannot_recur_terminates_without_round_cap():
    # a→b→a with a tempting cycle: equal energies give NO strict decrease, so the
    # loop is structurally impossible — no max_rounds knob involved.
    graph = {"a": ["b"], "b": ["a"]}
    energies = {"a": 1.0, "b": 1.0}
    res = _descender(graph, energies).settle("a")
    assert res.settled_state == "a" and res.steps_taken == 0
    assert res.local_minimum is True                      # honest 'no downhill from here'


def test_downhill_cycle_is_mathematically_impossible_to_construct():
    # any cycle needs energies e1>e2>...>e1 — a contradiction; the closest you can
    # build stalls at the cycle's minimum instead of spinning.
    graph = {"x": ["y"], "y": ["z"], "z": ["x"]}
    energies = {"x": 3.0, "y": 2.0, "z": 1.0}
    res = _descender(graph, energies).settle("x")
    assert res.settled_state == "z" and res.steps_taken == 2  # stops; never re-enters x


def test_implication_as_slope_follows_entailment():
    # P⇒Q taught as E(Q)<E(P): from P the ONLY downhill step is the valid inference,
    # even when a same-energy distractor is adjacent.
    graph = {"P": ["Q", "distractor"]}
    energies = {"P": 2.0, "Q": 1.0, "distractor": 2.0}
    res = _descender(graph, energies).settle("P")
    assert res.settled_state == "Q"


def test_runaway_neighbour_generator_is_bounded_defensively():
    desc = EnergyDescent(lambda s: -float(s), lambda s: iter(range(10 ** 9)), max_states=50)
    with pytest.raises(RuntimeError):
        desc.settle(0)
