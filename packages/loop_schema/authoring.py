# -*- coding: utf-8 -*-
"""D2 — a slot the schema could not derive becomes a request to AUTHOR one.

`meta_diagnose.propose_novel_module` raises NotImplementedError, and the measured coordinate for
where it should fire is a retrieval miss: `Cambridge` scored 0.596 against the Athens recipe and
honestly declined. Declining is right; declining and stopping is the gap. D1 makes the gap
addressable, because a loop with a missing slot is now a NAMED absence rather than a vague one.

WHAT IS AUTHORED, AND WHAT IS NOT. Not the step -- the step is the domain's work and no schema
implies it. What is authored is the progress measure: the function that turns whatever counters a
round happens to report into the one number that must rise. That is the piece a person usually
supplies by intuition, it is small and pure, and `code_reason.code_author` verifies every candidate
against a real test gate before returning it.

THE TEST IS GENERATED FROM THE TRACE, NEVER WRITTEN HERE. This is the whole discipline. If the
asserts came from me, the authored measure would be fitted to my idea of progress and the exercise
would be theatre. Instead the observed rounds supply the labels:

    the measure must never fall across a run          (from the rounds themselves)
    it must rise exactly on the rounds the loop said it moved   (from the loop's own boolean)

Those two properties cannot be satisfied by a constant, and cannot be satisfied by a clock -- which
is what makes them worth verifying rather than just checking a type.

NOTHING IS INSTALLED. This emits a Task and, if asked, the authored body. Writing it into the repo
is a separate operator-gated act (D4): authoring is unconstrained, installation is not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from packages.loop_schema.schema import Trace, _boolean, _fields, _numeric, _rose, read_schema


@dataclass(frozen=True)
class SlotRequest:
    """A named absence, with everything needed to fill it."""
    loop: str
    slot: str                       # "progress"
    params: tuple[str, ...]         # the counters a round reports
    label_field: str                # the loop's own "it moved" boolean, the source of truth
    rounds: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"loop": self.loop, "slot": self.slot, "params": list(self.params),
                "label_field": self.label_field, "rounds": self.rounds, "reason": self.reason}


def _label_field(runs_num: list[dict[str, list[float]]],
                 runs_bool: list[dict[str, list[bool]]]) -> str | None:
    """The boolean that behaves like "this round moved something".

    Chosen structurally: it must not be constant (a field that is always true says nothing), and
    across the runs it must be true on strictly more than none and fewer than all rounds. A loop
    reporting a flag that never varies has not told us where its progress was."""
    if not runs_bool:
        return None
    shared = set(runs_bool[0])
    for b in runs_bool[1:]:
        shared &= set(b)
    for name in sorted(shared):
        vals = [v for b in runs_bool for v in b[name]]
        if 0 < sum(vals) < len(vals):
            return name
    return None


def missing_progress(name: str, traces: Sequence[Trace]) -> SlotRequest | None:
    """Is this a loop that reports rounds but cannot say whether it is getting anywhere?

    Returns None when the schema is already complete -- there is nothing to author -- and None again
    when the trace carries no varying "it moved" signal, because then there are no labels and an
    authored measure could not be checked against anything."""
    runs = [[_fields(r) for r in t] for t in traces if t]
    if not runs:
        return None
    if read_schema(name, traces) is not None:
        return None                                # the slot is already there; do not invent a rival

    runs_num = [_numeric(r) for r in runs]
    runs_bool = [_boolean(r) for r in runs]
    label = _label_field(runs_num, runs_bool)
    if label is None:
        return None

    shared = set(runs_num[0])
    for n in runs_num[1:]:
        shared &= set(n)
    if not shared:
        return None
    return SlotRequest(
        loop=name, slot="progress", params=tuple(sorted(shared)), label_field=label,
        rounds=sum(len(r) for r in runs),
        reason=("rounds are reported and one of them is flagged as having moved, but no field "
                "accumulates: nothing here can serve as a termination rule"),
    )


def _rows(traces: Sequence[Trace], params: Sequence[str]) -> list[list[dict[str, float]]]:
    return [[{p: float(_fields(r)[p]) for p in params} for r in t] for t in traces if t]


def authoring_task(request: SlotRequest, traces: Sequence[Trace]) -> Any:
    """A `code_reason` Task whose asserts are the loop's own observed behaviour.

    The function name is derived from the loop so two requests never collide in the author's
    learned library."""
    from packages.code_reason.authorship_harness import Task

    fname = f"progress_{request.loop}".replace("-", "_")
    params = list(request.params)
    sig = f"def {fname}({', '.join(params)}):"

    body_rows = _rows(traces, params)
    labels = [[bool(_fields(r)[request.label_field]) for r in t] for t in traces if t]

    lines: list[str] = []
    for i, (rows, lab) in enumerate(zip(body_rows, labels)):
        calls = ", ".join(f"{fname}({', '.join(repr(r[p]) for p in params)})" for r in rows)
        lines.append(f"_v{i} = [{calls}]")
        lines.append(f"assert all(b >= a for a, b in zip(_v{i}, _v{i}[1:])), 'fell on run {i}'")
        lines.append(f"_r{i} = [_v{i}[0] > 0] + [b > a for a, b in zip(_v{i}, _v{i}[1:])]")
        lines.append(f"assert _r{i} == {lab!r}, 'rose on the wrong rounds of run {i}'")

    doc = (f"Return how far the {request.loop} loop has got, from the counters one round reports. "
           f"It must never fall across a run, and must rise on exactly the rounds where "
           f"`{request.label_field}` is true.")
    return Task(name=fname, signature=sig, docstring=doc, test="\n".join(lines))


@dataclass(frozen=True)
class AuthoredSlot:
    """What came back. `verified` means it passed the generated gate, nothing more."""
    loop: str
    slot: str
    body: str | None
    source: str
    verified: bool
    tried: int
    task_name: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def abstained(self) -> bool:
        return self.body is None

    def as_dict(self) -> dict[str, Any]:
        return {"loop": self.loop, "slot": self.slot, "body": self.body, "source": self.source,
                "verified": self.verified, "tried": self.tried, "abstained": self.abstained,
                "task": self.task_name, "notes": list(self.notes)}


def author_slot(request: SlotRequest, traces: Sequence[Trace], *, max_tries: int = 400,
                max_params: int = 3) -> AuthoredSlot:
    """Ask the code author to fill the slot, narrowest subset of the counters first.

    SUBSET SEARCH, and why it is not cheating. Measured on `code_author` directly: a two-parameter
    target of this shape is authored and verified in 4 tries; a three-parameter one enumerates 1134
    candidates and abstains; a five-parameter one reports `tried=0` -- the families do not open at
    all. Handing it all five counters is therefore a guaranteed abstention that says nothing.

    Choosing WHICH two would be me supplying the insight, so nothing chooses: subsets are
    enumerated smallest-first and every candidate faces the same generated trace gate. The search is
    mechanical and the verification is unchanged, which is the line between search and being told.

    Abstention across every subset is a real outcome and is reported as one, with the coordinate --
    how many subsets were tried and how deep -- so the next lever is a measurement rather than a
    guess."""
    from itertools import combinations

    from packages.code_reason.code_author import author

    tried_total = 0
    subsets = 0
    for size in range(2, max(2, min(max_params, len(request.params))) + 1):
        for chosen in combinations(request.params, size):
            subsets += 1
            narrowed = SlotRequest(
                loop=request.loop, slot=request.slot, params=chosen,
                label_field=request.label_field, rounds=request.rounds, reason=request.reason)
            task = authoring_task(narrowed, traces)
            got = author(task, max_tries=max_tries)
            tried_total += got.tried
            if got.verified and got.body:
                return AuthoredSlot(
                    loop=request.loop, slot=request.slot, body=got.body, source=got.source,
                    verified=True, tried=tried_total, task_name=task.name,
                    notes=(f"from {len(chosen)} of {len(request.params)} counters: "
                           f"{', '.join(chosen)}",
                           f"{subsets} subsets tried"))

    return AuthoredSlot(
        loop=request.loop, slot=request.slot, body=None, source="none", verified=False,
        tried=tried_total, task_name=f"progress_{request.loop}",
        notes=("author abstained; the slot stays a named absence",
               f"{subsets} subsets up to {max_params} counters, {tried_total} candidates"),
    )
