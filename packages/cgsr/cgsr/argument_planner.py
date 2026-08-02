# -*- coding: utf-8 -*-
"""Plan a FREE argument shape by walking the learned move-transition model (argument_miner).

This is the piece that makes an argument free instead of templated. The old path emitted one fixed
move order for every argument. Here the order is SAMPLED from P(next|cur) that was mined from real
prose — so it varies with context and reflects how humans actually sequence moves, and nothing about
the order is hand-written. The planner only enforces two structural facts that are definitional, not
stylistic: an argument opens by asserting something (start ≈ CLAIM, itself the mined start-dominant),
and it is finite (a length cap). Everything between is the learned walk.

Determinism: seeded by the discussion context so a given state yields a stable plan (reproducible,
auditable), yet different states — different opponents, different turns — yield different shapes.
"""
from __future__ import annotations

import random

from .argument_miner import MOVES, load_model

# A tiny built-in fallback transition model (used only if the mined file is absent), so the planner
# still runs before/without a corpus. Numbers are a coarse prior, immediately overridden by mining.
_FALLBACK = {
    "start": {"CLAIM": 1.0},
    "end": {"IMPLICATION": 0.4, "QUALIFY": 0.2, "REBUTTAL": 0.2, "CLAIM": 0.2},
    "transitions": {
        "CLAIM": {"GROUND": 0.4, "REBUTTAL": 0.25, "IMPLICATION": 0.15, "CONCESSION": 0.1, "EXAMPLE": 0.1},
        "GROUND": {"IMPLICATION": 0.4, "CLAIM": 0.2, "EXAMPLE": 0.2, "REBUTTAL": 0.2},
        "CONCESSION": {"REBUTTAL": 0.6, "GROUND": 0.2, "CLAIM": 0.2},
        "REBUTTAL": {"GROUND": 0.4, "IMPLICATION": 0.3, "CLAIM": 0.3},
        "EXAMPLE": {"IMPLICATION": 0.5, "CLAIM": 0.3, "REBUTTAL": 0.2},
        "IMPLICATION": {"QUALIFY": 0.4, "CLAIM": 0.3, "REBUTTAL": 0.3},
        "QUALIFY": {"CLAIM": 0.5, "IMPLICATION": 0.5},
    },
}


def _model() -> dict:
    m = load_model()
    if m and m.get("transitions"):
        return m
    return _FALLBACK


def _sample(dist: dict, rng: random.Random, exclude: set | None = None) -> str | None:
    items = [(k, v) for k, v in (dist or {}).items() if not exclude or k not in exclude]
    if not items:
        return None
    keys, weights = zip(*items)
    return rng.choices(keys, weights=weights, k=1)[0]


def plan_moves(seed: int = 0, *, min_len: int = 3, max_len: int = 5,
               force_concession: bool = False, model: dict | None = None) -> list[str]:
    """Return a free sequence of DISTINCT argument moves (consecutive repeats collapsed). The walk
    follows the learned transitions; length lands in [min_len, max_len] but is not otherwise shaped.

    force_concession: when the turn is responding to a live opponent, bias the walk to include one
    CONCESSION→REBUTTAL (the 'yes-but' the corpus itself makes most likely after a concession) — this
    is not a hardcoded slot, it just seeds the walk through a state the model already favours here.
    """
    m = model or _model()
    trans = m.get("transitions", {})
    start = m.get("start", {"CLAIM": 1.0})
    end = m.get("end", {})
    rng = random.Random(seed)

    cur = _sample(start, rng) or "CLAIM"
    plan = [cur]
    guard = 0
    while len(plan) < max_len and guard < max_len * 4:
        guard += 1
        nxt = _sample(trans.get(cur, {}), rng)
        if nxt is None:
            break
        if nxt == plan[-1]:
            # a self-loop means 'stay on this move' — for realization we render each move once, so a
            # loop is a weak stop signal: past min_len, honour the model's tendency to end.
            if len(plan) >= min_len and rng.random() < 0.5:
                break
            # else re-sample once, excluding the just-used move, to keep the argument moving
            nxt = _sample(trans.get(cur, {}), rng, exclude={cur})
            if nxt is None:
                break
        plan.append(nxt)
        cur = nxt
        # stochastic stop weighted by how often this move ENDS an argument in the corpus
        if len(plan) >= min_len and rng.random() < end.get(cur, 0.0):
            break

    if force_concession and "CONCESSION" not in plan and len(plan) >= 2:
        # insert the concede-then-rebut pair at the position the walk is most receptive to it: right
        # after the opening claim. REBUTTAL follows because that is the mined top successor of
        # CONCESSION (0.22) — the data chooses the pairing, we only place the pair.
        plan[1:1] = ["CONCESSION", "REBUTTAL"]

    # collapse any accidental consecutive duplicates and cap length
    out: list[str] = []
    for mv in plan:
        if not out or out[-1] != mv:
            out.append(mv)
    return out[:max_len]


def describe_plan(plan: list[str]) -> str:
    """Human-readable trace of the chosen argument shape (XAI: every argument exposes its structure)."""
    return " → ".join(plan)
