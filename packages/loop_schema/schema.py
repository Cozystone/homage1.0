# -*- coding: utf-8 -*-
"""D1 — what a loop IS, read off loops that work, so a new one can be authored against it.

A loop is four slots: a step, a progress measure, a termination rule, and stall detection. The step
is whatever the domain is doing. The other three are the part that is generic, and they are the part
that is hard: what is common to every loop is not the work, it is the ARITHMETIC OF KNOWING WHETHER
THE WORK IS GETTING ANYWHERE. That arithmetic is small pure functions over numbers, which is exactly
what `code_reason.code_author` can author and verify.

READ FROM BEHAVIOUR, NOT FROM NAMES. The obvious implementation looks for attributes called
`improved` and `stalled`, and that is a hand list of two names wearing a schema's clothes -- the same
move that made `sealed_evidence` a filename artifact and that mis-credited `base_brain` in the
receipt census, both today. So the slots are derived from TRACES: run a real loop, and

  * the PROGRESS slot is a numeric field that never falls across the run and rises at least once;
  * the STALLED slot is a boolean that is true exactly on the rounds where progress did not rise;
  * the IMPROVED slot is its complement.

Nothing here knows what those fields are called. Fed the repair loop it finds them; fed a loop that
spells them differently it finds those instead; fed something that is not a loop it returns None
rather than a flattering guess.

WHY MULTIPLE TRACES. One run leaves the slot under-determined -- on the real Athens run `placed`,
`foreign`, `referents` and `resolution` are all non-decreasing, and each of them "agrees" with the
booleans. A measure that only works on one subject is not a progress measure, it is a coincidence,
so agreement is required across every trace supplied and ties are broken toward the measure that is
BOUNDED: a rate in [0,1] is comparable between subjects and a raw count is not, which is what makes
it usable as a termination rule rather than just a number that went up.

The two loops this was read off disagree about their reference point, which is why the derivation
cannot assume one: `PurificationRound` compares before/after WITHIN a round, `RoundResult` compares
against the previous round's total. Both are "did anything move", measured from different places.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

Trace = Sequence[Any]


@dataclass(frozen=True)
class LoopSchema:
    """The three derivable slots of a loop, plus how they were derived."""
    name: str
    progress: str
    improved: str | None
    stalled: str | None
    traces: int
    rounds: int
    candidates: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        """A loop that can measure progress AND detect a stall. Without the second it runs
        forever; without the first it cannot tell motion from progress."""
        return bool(self.progress) and self.stalled is not None

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "progress": self.progress, "improved": self.improved,
                "stalled": self.stalled, "traces": self.traces, "rounds": self.rounds,
                "complete": self.complete, "progress_candidates": list(self.candidates)}


def _fields(obj: Any) -> dict[str, Any]:
    """Every readable scalar this round exposes, attributes and properties alike.

    Properties matter: `RoundResult.resolution` and `.stalled` are computed, and a reader that only
    saw dataclass fields would miss the entire answer."""
    out: dict[str, Any] = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            val = getattr(obj, name)
        except Exception:
            continue
        if isinstance(val, bool) or isinstance(val, (int, float)):
            out[name] = val
    return out


def _numeric(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    if not rows:
        return {}
    shared = set(rows[0])
    for r in rows[1:]:
        shared &= set(r)
    return {k: [float(r[k]) for r in rows]
            for k in sorted(shared) if all(not isinstance(r[k], bool) for r in rows)}


def _boolean(rows: list[dict[str, Any]]) -> dict[str, list[bool]]:
    if not rows:
        return {}
    shared = set(rows[0])
    for r in rows[1:]:
        shared &= set(r)
    return {k: [bool(r[k]) for r in rows]
            for k in sorted(shared) if all(isinstance(r[k], bool) for r in rows)}


def _rose(series: Sequence[float]) -> list[bool]:
    """Per round: did this measure rise against the round before it?

    The first round is compared against zero, not against nothing: a loop that settles something on
    its first pass has improved, and treating round one as unknowable would make every single-round
    loop look stalled."""
    out = [series[0] > 0.0]
    for prev, cur in zip(series, series[1:]):
        out.append(cur > prev)
    return out


def _bounded(name: str, per_trace: list[list[float]]) -> bool:
    return all(0.0 <= v <= 1.0 for vals in per_trace for v in vals)


def read_schema(name: str, traces: Iterable[Trace]) -> LoopSchema | None:
    """Derive the slots from how the loop behaved. None when the traces do not describe a loop.

    Returning None is the honest outcome for a sequence with no monotone measure -- something that
    changes state without accumulating anything is a process, not a loop with progress, and calling
    it one would put a termination rule on a quantity that can fall."""
    runs = [[_fields(r) for r in t] for t in traces if t]
    runs = [r for r in runs if len(r) >= 1]
    if not runs:
        return None

    per_run_numeric = [_numeric(r) for r in runs]
    per_run_boolean = [_boolean(r) for r in runs]
    shared_num = set(per_run_numeric[0])
    for n in per_run_numeric[1:]:
        shared_num &= set(n)
    if not shared_num:
        return None

    # a progress candidate must be monotone in EVERY run, and rise somewhere
    cands = []
    for field_name in sorted(shared_num):
        series = [n[field_name] for n in per_run_numeric]
        if all(all(b >= a for a, b in zip(s, s[1:])) for s in series) and \
           any(any(b > a for a, b in zip(s, s[1:])) or (len(s) == 1 and s[0] > 0) for s in series):
            cands.append(field_name)
    if not cands:
        return None

    # A CLOCK IS NOT PROGRESS. `round_index` is monotone in every run and survived the filter above
    # on the real repair traces -- a counter always rises, which makes it a perfect-looking and
    # completely empty progress measure. What separates progress from a clock is that progress CAN
    # FAIL TO RISE: a round that settles nothing must show it. Candidates that rise on every round
    # of every run are dropped whenever any candidate does not, and kept only when none does, since
    # then no stall was ever observed and the schema is incomplete regardless.
    def _always_rises(fname: str) -> bool:
        return all(all(rose) for rose in (_rose(n[fname]) for n in per_run_numeric))
    discriminating = [c for c in cands if not _always_rises(c)]
    if not discriminating:
        # Every surviving candidate rose on every round, so no stall was ever observed and a clock
        # is indistinguishable from progress on this evidence. Measured why None beats a guess: on a
        # run whose real measure stayed flat at 0.0, the round counter was the only riser, won the
        # slot, and dragged the booleans in BACKWARDS -- `improved` bound to the field meaning
        # "nothing moved", because the complement agreed just as well. A schema derived from
        # behaviour cannot name a slot the behaviour never exercised.
        return None

    # a boolean slot must agree with "progress rose" on every round of every run
    def _agreeing(field_name: str, want_rose: bool) -> str | None:
        shared_bool = set(per_run_boolean[0])
        for b in per_run_boolean[1:]:
            shared_bool &= set(b)
        for bname in sorted(shared_bool):
            ok = True
            for nrun, brun in zip(per_run_numeric, per_run_boolean):
                rose = _rose(nrun[field_name])
                want = rose if want_rose else [not x for x in rose]
                if brun[bname] != want:
                    ok = False
                    break
            if ok:
                return bname
        return None

    # prefer a candidate that a boolean actually tracks; among those, prefer a bounded rate.
    # `cands` stays the FULL monotone set for reporting -- what was considered and rejected is part
    # of the finding, and narrowing it in place would hide that a clock was in the running.
    scored = []
    for c in discriminating:
        stalled = _agreeing(c, want_rose=False)
        improved = _agreeing(c, want_rose=True)
        bounded = _bounded(c, [n[c] for n in per_run_numeric])
        scored.append((stalled is not None, improved is not None, bounded, c, stalled, improved))
    scored.sort(reverse=True)
    _, _, _, best, stalled, improved = scored[0]

    return LoopSchema(name=name, progress=best, improved=improved, stalled=stalled,
                      traces=len(runs), rounds=sum(len(r) for r in runs),
                      candidates=tuple(cands))


@dataclass(frozen=True)
class Conformance:
    """Whether a trace behaves the way its schema says it does."""
    schema: str
    rounds: int
    monotone: bool
    stall_agrees: bool
    terminated_on_stall: bool

    @property
    def ok(self) -> bool:
        return self.monotone and self.stall_agrees and self.terminated_on_stall


def conforms(trace: Trace, schema: LoopSchema) -> Conformance:
    """Check a run against the schema derived from other runs.

    `terminated_on_stall` is the property that distinguishes a loop from a fixed-count pass: the run
    has to END where the stall was detected. A run that stalls in the middle and keeps going is
    spending rounds it already knows are worthless."""
    rows = [_fields(r) for r in trace]
    if not rows:
        return Conformance(schema.name, 0, False, False, False)
    vals = [float(r[schema.progress]) for r in rows] if schema.progress in rows[0] else []
    monotone = bool(vals) and all(b >= a for a, b in zip(vals, vals[1:]))
    stall_agrees = terminated = False
    if schema.stalled and vals and schema.stalled in rows[0]:
        flags = [bool(r[schema.stalled]) for r in rows]
        stall_agrees = flags == [not x for x in _rose(vals)]
        terminated = flags[-1] and not any(flags[:-1])
    return Conformance(schema.name, len(rows), monotone, stall_agrees, terminated)
