# -*- coding: utf-8 -*-
"""The improvement-cycle ledger — is this project compounding, or just accumulating?

    from packages.meta_diagnosis.improvement_cycles import record, trajectory
    record(Cycle(name="E5-2", failure_found_by="human", gain=0.053, ...))
    print(trajectory())      # gain per cycle, cycle time, and who found the failure

THE QUESTION THIS EXISTS TO SETTLE. "When will ATANOR improve itself exponentially" is asked as a
prediction and answered with adjectives. It is a MEASUREMENT, and the measurement is cheap: log each
improvement cycle and look at whether the gains hold up.

Exponential self-improvement is not "the system changed itself". It is a specific, checkable shape:

    gain per cycle does not shrink        cycle N's gain >= cycle N-1's
    OR cycle time shrinks while gain holds
    AND the system finds its own failures  human_touches per cycle -> 0

All three are numbers. Two cycles are on the board so far and they do not tell a flattering story:

    E5-1  +19.7%  failure found by human, one session
    E5-2   +5.3%  failure found by human, one session

A quarter of the gain on the second turn, with the cycle time flat and every failure still found by a
person. That is diminishing returns on the easy fruit, which is the ordinary and expected shape -- and
it is the opposite of the exponential story. Recording it is the point: a ledger that only held wins
would make the trajectory unfalsifiable.

THE DISTINCTION THAT ACTUALLY DECIDES IT, and the one this ledger is built around: a cycle can improve
the PRODUCT or improve the CAPACITY TO IMPROVE. Both feel like progress; only the second compounds.
Raising fact yield 5% does not make the next failure easier to find. So every cycle records which kind
it was, and `trajectory()` reports them separately -- because a hundred product cycles in a row is a
straight line no matter how good each one felt.

WIREHEADING IS THE LIVE RISK, not a theoretical one. In cycle E5-2 the miss ranking said to add
`consisting of` -- the largest single class of failures. Following it would have mapped "the United
States consists of fifty states" onto `made_of`, improving the metric while degrading the graph. A loop
that optimises its own score without judgment does exactly that. So a cycle records what it REFUSED as
well as what it did; a ledger of only actions cannot show restraint being exercised.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

LEDGER = Path("data/meta_diagnosis/improvement_cycles.jsonl")

KIND_PRODUCT = "product"        # the system got better at its job
KIND_CAPACITY = "capacity"      # the system got better at IMPROVING -- the only kind that compounds


@dataclass
class Cycle:
    """One turn of find-failure -> change -> measure. Everything here is observed, not estimated."""

    name: str
    kind: str                       # product | capacity
    gain: float                     # relative improvement on the cycle's own sealed metric
    metric: str                     # what the gain is measured on, named so it can be re-run
    failure_found_by: str           # "human" | "atanor" | "harness" -- the number that must reach atanor
    human_touches: int              # how many distinct human interventions the cycle needed
    sessions: float                 # cycle time, in working sessions
    at: str = ""                    # ISO date; passed in, never guessed
    refused: str = ""               # what the cycle declined to do, and why
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def record(cycle: Cycle) -> None:
    """Append a cycle. Append-only by intent: a ledger that can be edited is a story, not a record."""
    if cycle.kind not in (KIND_PRODUCT, KIND_CAPACITY):
        raise ValueError(f"kind must be {KIND_PRODUCT!r} or {KIND_CAPACITY!r}, got {cycle.kind!r}")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(cycle.as_dict(), ensure_ascii=False) + "\n")


def _rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def trajectory() -> dict:
    """Are the gains holding up, is the cycle getting cheaper, and who is finding the failures.

    Returns the three numbers the exponential claim would have to move, and refuses to summarise them
    into a single verdict -- a 'compounding: yes/no' field would be exactly the kind of adjective this
    module exists to replace."""
    rows = _rows()
    if not rows:
        return {"cycles": 0, "note": "no cycles recorded"}
    gains = [r.get("gain", 0.0) for r in rows]
    capacity = [r for r in rows if r.get("kind") == KIND_CAPACITY]
    self_found = [r for r in rows if r.get("failure_found_by") == "atanor"]
    deltas = [round(gains[i] - gains[i - 1], 4) for i in range(1, len(gains))]
    # A WINDOW, NOT ALL OF HISTORY -- and the first version was unachievable by construction.
    # `all(d >= 0)` over every delta ever recorded can never become true once a single cycle has
    # declined, and one had by the second cycle. A metric that no future behaviour can move reports
    # nothing about behaviour; it only reports that the past happened.
    #
    # The question this series exists to answer is "is it compounding NOW", so it reads the last
    # three deltas. The window was fixed BEFORE checking whether it helped -- it does not: the last
    # three are [+0.019, -0.019, +0.066] and still contain a decline. Choosing a window that made the
    # metric pass would be wireheading on the one instrument built to detect wireheading.
    window = deltas[-3:]
    return {
        "cycles": len(rows),
        "gain_per_cycle": [round(g, 4) for g in gains],
        "gain_deltas": deltas,
        "gains_holding": all(d >= 0 for d in window) if window else None,
        "gains_holding_window": window,
        "gains_holding_all_time": all(d >= 0 for d in deltas) if deltas else None,
        "capacity_cycles": len(capacity),
        "product_cycles": len(rows) - len(capacity),
        "failure_found_by": [r.get("failure_found_by") for r in rows],
        "failures_found_by_atanor": f"{len(self_found)}/{len(rows)}",
        "human_touches_per_cycle": [r.get("human_touches") for r in rows],
        "sessions_per_cycle": [r.get("sessions") for r in rows],
        "refusals_recorded": sum(1 for r in rows if r.get("refused")),
        "reading": ("compounding requires gains that do not shrink, OR cycle time that does, AND "
                    "failures the system finds itself. These are the three series; the verdict is "
                    "not summarised here on purpose."),
    }
