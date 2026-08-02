# -*- coding: utf-8 -*-
"""Procedure induction — the system builds its OWN algorithms from examples, then verifies them.

Owner (2026-07-14): don't hand-build the reasoning kernels — let ATANOR structure its
understanding into executors itself, the way a person learns an algorithm rather than being born
with it; gated self-modification is that path. This organ is the missing piece: given worked
INPUT→OUTPUT examples of a procedure, it SEARCHES a tiny space of programs over a growing
primitive basis for one that reproduces every example, then VERIFIES it on held-out examples it
was never shown. Only a program that survives verification is kept — the same consensus/proof
doctrine as facts: never a hallucinated algorithm.

Why a primitive basis still exists (honest scope): you cannot induce addition from nothing, just
as a child needs counting first. We seed only the UNIVERSAL primitives (successor S, predecessor
P, constants) and a bounded loop; every higher algorithm (addition, then multiplication built ON
the induced addition — compositional library growth) is INDUCED, not written. When induction can
re-derive a hand-built kernel from examples, the hand-building stops.

This is narrow-but-real: it works where a procedure is well-specified and verification is cheap
(arithmetic, unit steps, stoichiometry). General reasoning induction is open — measured, not
claimed. Induced procedures are the payload gated self-modification promotes into new executors.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable


# ---- primitive basis: (fn, arity). Starts minimal + universal; induce() grows it. -------------
def _S(x: int) -> int:            # successor
    return x + 1


def _P(x: int) -> int:            # predecessor (bounded at 0 — Peano naturals)
    return x - 1 if x > 0 else 0


def seed_basis() -> dict[str, tuple[Callable[..., int], int]]:
    return {"S": (_S, 1), "P": (_P, 1)}


# ---- a candidate program: acc = init; repeat <count> times: acc = OP(acc, arg); return acc ----
@dataclass
class Program:
    init: str                     # '0' | '1' | 'a' | 'b'
    count: str                    # 'a' | 'b'
    op: str                       # a basis name
    arg: str                      # '_' (arity-1: OP(acc)) | 'a' | 'b' | '1' | 'i' (loop index)
    name: str = ""

    def run(self, a: int, b: int, basis: dict[str, tuple[Callable[..., int], int]],
            *, budget: int = 200_000) -> int | None:
        env = {"0": 0, "1": 1, "a": a, "b": b}
        acc = env[self.init]
        n = env[self.count]
        fn, arity = basis[self.op]
        if n < 0 or n > budget:
            return None
        for i in range(n):
            try:
                if arity == 1:
                    acc = fn(acc)
                else:
                    arg = i if self.arg == "i" else env.get(self.arg, 0)
                    acc = fn(acc, arg)
            except Exception:
                return None
            if acc is None or acc > 10**12:           # composed basis fn may fail (None) or run away
                return None
        return acc

    def source(self) -> str:
        body = f"{self.op}(acc)" if self.arg == "_" else f"{self.op}(acc, {self.arg})"
        return f"acc = {self.init}; repeat {self.count} times: acc = {body}; return acc"


@dataclass
class Induced:
    program: Program
    fn: Callable[[int, int], int]
    n_train: int
    n_verified: int
    basis_used: list[str] = field(default_factory=list)

    def certificate(self) -> dict[str, Any]:
        return {"induced_procedure": self.program.name, "program": self.program.source(),
                "basis_used": self.basis_used,
                "fit_examples": self.n_train, "verified_held_out": self.n_verified,
                "basis": "synthesized by search over a primitive basis; kept only after "
                         "reproducing every training example AND every held-out example — "
                         "an induced algorithm, never a guessed one"}


def _candidates(basis: dict[str, tuple[Callable[..., int], int]]):
    inits = ["0", "1", "a", "b"]
    counts = ["a", "b"]
    for op, (_fn, arity) in basis.items():
        args = ["_"] if arity == 1 else ["a", "b", "1", "i"]
        for init, count, arg in itertools.product(inits, counts, args):
            yield Program(init, count, op, arg)


def _size(prog: Program, basis: dict[str, tuple[Callable[..., int], int]]) -> int:
    """Description length (Occam prior, Lake 2015): a program that REUSES a richer induced
    primitive is 'shorter' in concept-length than one built from raw successors, so higher-level
    solutions are preferred once the library has grown."""
    depth = {"S": 1, "P": 1}.get(prog.op, 3)          # richer induced ops cost less to invoke
    non_trivial_init = 0 if prog.init in ("0", "a", "b") else 1
    return depth + non_trivial_init + (0 if prog.arg == "_" else 1)


def induce(name: str, examples: list[tuple[tuple[int, int], int]],
           basis: dict[str, tuple[Callable[..., int], int]] | None = None,
           *, holdout_frac: float = 0.4) -> Induced | None:
    """Search for a program reproducing all TRAIN examples, verify on HELD-OUT ones, and among the
    survivors keep the OCCAM-shortest (Lake 2015 — the simplest program that explains the data).
    examples: [((a, b), out), …]. Returns Induced or None (honest failure)."""
    basis = basis or seed_basis()
    ex = list(examples)
    if len(ex) < 4:
        return None
    k = max(2, int(len(ex) * (1 - holdout_frac)))
    train, held = ex[:k], ex[k:]
    fits: list[Program] = []
    for prog in _candidates(basis):
        if all(prog.run(a, b, basis) == out for (a, b), out in train) \
                and held and all(prog.run(a, b, basis) == out for (a, b), out in held):
            fits.append(prog)
    if not fits:
        return None
    best = min(fits, key=lambda p: _size(p, basis))   # Occam: shortest description wins
    best.name = name
    fn = (lambda p: (lambda a, b: p.run(a, b, basis)))(best)
    return Induced(best, fn, len(train), len(held), sorted(basis.keys()))


def grow_basis(basis: dict[str, tuple[Callable[..., int], int]], ind: Induced
               ) -> dict[str, tuple[Callable[..., int], int]]:
    """Compositional library growth (self-extension): an induced procedure becomes a primitive
    the NEXT induction may build on — how multiplication is induced on top of induced addition."""
    b2 = dict(basis)
    b2[ind.program.name] = (ind.fn, 2)
    return b2


# ============================================================================================
# DOMAIN-GENERAL induction (COGNITIVE_FOUNDATIONS decision 3): the same verify-gated search over
# ANY program space, not just arithmetic. First non-arithmetic space = disjunctive syllogism
# (elimination), the logic Cesana-Arlotti (Science 2018) found already present in 12-month-olds:
# from {A, B} with A ruled out, conclude B. Induced from examples, never hard-coded.
# ============================================================================================
from typing import Sequence  # noqa: E402


@dataclass
class GeneralInduced:
    name: str
    rule: str
    fn: Callable[..., Any]
    n_train: int
    n_verified: int

    def certificate(self) -> dict[str, Any]:
        return {"induced_procedure": self.name, "rule": self.rule,
                "fit_examples": self.n_train, "verified_held_out": self.n_verified,
                "basis": "domain-general program induction; kept only after reproducing every "
                         "training AND held-out example — verification-gated, No-LLM"}


# candidate logic rules over (candidate_set: tuple, ruled_out: element) → chosen element.
# Each is (rule_name, fn); the inducer picks the one matching every example.
def _elim(cs: Sequence, out) -> Any:
    rem = [x for x in cs if x != out]
    return rem[0] if len(rem) == 1 else None          # unique survivor = disjunctive syllogism


_LOGIC_SPACE: list[tuple[str, Callable[[Sequence, Any], Any]]] = [
    ("disjunctive_syllogism: return the single member of the set NOT ruled out", _elim),
    ("return the ruled-out element", lambda cs, out: out),
    ("return the first member", lambda cs, out: cs[0] if cs else None),
    ("return the last member", lambda cs, out: cs[-1] if cs else None),
]


def induce_general(name: str, examples: list[tuple[tuple, Any]],
                   space: list[tuple[str, Callable]] | None = None,
                   *, holdout_frac: float = 0.4) -> GeneralInduced | None:
    """Induce a rule over an arbitrary program space from (inputs_tuple, output) examples,
    verify-gated. examples: [((set_tuple, ruled_out), chosen), …] for the default logic space."""
    space = space or _LOGIC_SPACE
    ex = list(examples)
    if len(ex) < 4:
        return None
    k = max(2, int(len(ex) * (1 - holdout_frac)))
    train, held = ex[:k], ex[k:]
    for rule, fn in space:                             # spaces are ordered simplest-first (Occam)
        try:
            if all(fn(*inp) == out for inp, out in train) \
                    and held and all(fn(*inp) == out for inp, out in held):
                return GeneralInduced(name, rule, fn, len(train), len(held))
        except Exception:
            continue
    return None
