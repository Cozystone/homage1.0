# -*- coding: utf-8 -*-
"""Induction flywheel — prediction-error-driven self-modification + LEARNED search guidance.

Owner (2026-07-14): the strongest engine of human cognitive growth is the VERIFICATION FLYWHEEL —
act on a self-derived rule, and when the world contradicts it (prediction error), modify the
cognitive structure; repeated, this turns shallow memory into deep reasoning. This module is that
loop for induced procedures, and it also closes the learned-search frontier:

  LEDGER      every induced procedure is a living HYPOTHESIS with usage stats and confidence.
  ERROR→FIX   a prediction error (output ≠ verified truth) writes an error receipt, adds the
              counterexample to the procedure's examples, RE-INDUCES, and tombstones the old
              version — structure modification, gated by the same held-out verification.
  DREAMING    the system samples programs from its own library, executes them to synthesize
              example sets, and learns a PROPOSAL DISTRIBUTION: problem-signature → program
              skeletons. Self-generated data only — zero test contamination.
  GUIDED      induction tries candidates in learned-probability order instead of brute force.
              The guide only PROPOSES; the verify gate still DISPOSES — a corrupted guide can
              slow search but can never admit a wrong algorithm.

Measured, not claimed: guided_induce reports how many candidates it tried; the test suite
asserts a real reduction vs brute force on tasks the dreamer never saw verbatim.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .procedure_induction import (Induced, Program, _candidates, _size, grow_basis,  # noqa: F401
                                  induce, seed_basis)

_ROOT = Path(__file__).resolve().parents[2]
_LEDGER = _ROOT / "data" / "reasoning" / "hypothesis_ledger.jsonl"

Basis = dict[str, tuple[Callable[..., int], int]]
Example = tuple[tuple[int, int], int]


# ---------------------------------------------------------------- hypothesis ledger
def _append_ledger(row: dict[str, Any]) -> None:
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record_induced(ind: Induced, *, tried: int, guided: bool) -> None:
    _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "induced",
                    "name": ind.program.name, "program": ind.program.source(),
                    "skeleton": _skeleton(ind.program), "tried_candidates": tried,
                    "guided": guided, "verified_held_out": ind.n_verified, "confidence": 0.9})


def record_error(name: str, program: Program, counterexample: Example, expected: int,
                 got: int | None) -> None:
    """A prediction error: the procedure's output disagreed with verified truth."""
    (a, b), out = counterexample
    _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "prediction_error",
                    "name": name, "program": program.source(),
                    "input": [a, b], "expected": expected, "got": got})


def record_tombstone(name: str, old: Program, reason: str) -> None:
    _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "tombstone",
                    "name": name, "program": old.source(), "reason": reason})


# ---------------------------------------------------------------- problem features
def _features(examples: list[Example]) -> set[str]:
    """The SET of structural features an example set exhibits — what a person notices before
    solving: identity elements, growth shape, functional dependence, curvature. Each feature is an
    INDEPENDENT cue. The guide scores skeletons per-feature (PMI), so a novel family that shares
    individual features with dreamed ones still gets a proposal (extrapolation) — and adding a
    feature never fragments a bucket, because features vote independently, not as a combined key.
    Never the answer itself."""
    feats: set[str] = set()
    vm = [("gt" if out > max(a, b) else "eq" if out == max(a, b) else "lt") for (a, b), out in examples]
    feats.add("vsmax:" + max(sorted(set(vm)), key=vm.count))   # sorted: tie-break is hash-seed-free
    for (a, b), out in examples:                        # identity signals (b=0 / a=0 behaviour)
        if b == 0:
            feats.add("b0:id" if out == a else ("b0:zero" if out == 0 else "b0:other"))
        if a == 0:
            feats.add("a0:id" if out == b else ("a0:zero" if out == 0 else "a0:other"))
    n = max(1, len(examples))
    feats.add("addlike:" + ("hi" if sum(1 for (a, b), o in examples if o == a + b) / n > 0.6 else "lo"))
    feats.add("mullike:" + ("hi" if sum(1 for (a, b), o in examples if o == a * b) / n > 0.6 else "lo"))
    # functional dependence — which input alone determines the output (needs a repeated coordinate
    # to observe). General cue for the loop VARIABLE (count=a / count=b / arg=i). SAFE now: with
    # per-feature PMI scoring it is an extra independent voter, not a bucket split.
    by_a: dict[int, set[int]] = defaultdict(set)
    by_b: dict[int, set[int]] = defaultdict(set)
    for (a, b), out in examples:
        by_a[a].add(out); by_b[b].add(out)
    a_det = len(by_a) < len(examples) and all(len(v) == 1 for v in by_a.values())
    b_det = len(by_b) < len(examples) and all(len(v) == 1 for v in by_b.values())
    det = "a" if (a_det and not b_det) else "b" if (b_det and not a_det) else None
    if det:
        feats.add("det:" + det)
        # growth curvature in the determining variable: linear (add-like) vs convex (mul/pow-like)
        pts = sorted(((a if det == "a" else b), out) for (a, b), out in examples)
        difs = [pts[i + 1][1] - pts[i][1] for i in range(len(pts) - 1)]
        if len(difs) >= 2:
            d2 = sum((difs[i + 1] - difs[i]) for i in range(len(difs) - 1))
            feats.add("curv:up" if d2 > 0 else "curv:flat" if d2 == 0 else "curv:dn")
    return feats


def signature(examples: list[Example]) -> str:
    """Human-readable join of the feature set (interpretability + ledger); the guide itself scores
    per-feature, not on this exact string."""
    return "|".join(sorted(_features(examples)))


def _skeleton(p: Program) -> str:
    return f"{p.init}/{p.count}/{p.op}/{p.arg}"


# ---------------------------------------------------------------- dreaming → learned guide
class SearchGuide:
    """FEATURIZED recognition model: learns, per INDEPENDENT feature, which skeletons co-occur, and
    scores a query skeleton by summing pointwise mutual information (PMI) over the query's features.
    This is what makes the guide EXTRAPOLATE — a family whose exact signature was never dreamed
    still gets a strong proposal if its individual features (det:a, curv:up, …) were seen with the
    right skeleton in OTHER dreamed families. Exact-signature lookup could only interpolate; per-
    feature PMI generalizes, and adding features never fragments (they vote independently). Learns
    from DREAMS (self-generated program+example pairs) and from real induction successes/errors.
    Interpretable and instantly updatable; the same interface can later hold a tiny MLP."""

    def __init__(self) -> None:
        self.table: dict[str, Counter[str]] = defaultdict(Counter)   # feature → skeleton counts
        self.ftot: Counter[str] = Counter()                          # observations carrying feature
        self.stot: Counter[str] = Counter()                          # skeleton prior counts
        self.n: int = 0                                              # total observations

    def _learn(self, examples: list[Example], skel: str, weight: int = 1) -> None:
        self.stot[skel] += weight
        self.n += weight
        for f in _features(examples):
            self.table[f][skel] += weight
            self.ftot[f] += weight

    def dream(self, basis: Basis, *, rounds: int = 400, seed: int = 11) -> int:
        """Sleep phase: sample programs from the CURRENT library, run them on small inputs to
        synthesize example sets, and learn (feature → skeleton) co-occurrences. Self-generated."""
        import random
        rng = random.Random(seed)
        cands = list(_candidates(basis))
        learned = 0
        for _ in range(rounds):
            prog = rng.choice(cands)
            pairs: list[Example] = []
            ok = True
            for a, b in [(rng.randint(0, 9), rng.randint(0, 9)) for _ in range(6)]:
                v = prog.run(a, b, basis)
                if v is None:
                    ok = False
                    break
                pairs.append(((a, b), v))
            if not ok:
                continue
            self._learn(pairs, _skeleton(prog))
            learned += 1
        return learned

    def order(self, examples: list[Example], basis: Basis) -> list[Program]:
        """Candidates ranked by summed positive PMI over the query's features (extrapolates), with
        Occam size as the tiebreak. A skeleton with no positive feature-evidence scores 0 and falls
        to size order — 'first, do no harm': the guide only promotes what it has real evidence for.
        Complete search is preserved (every candidate is still in the list)."""
        feats = _features(examples)
        cands = list(_candidates(basis))

        def score(p: Program) -> float:
            s = _skeleton(p)
            if self.n == 0 or self.stot[s] == 0:
                return 0.0
            tot = 0.0
            for f in sorted(feats):     # sorted: float-sum order fixed → hash-seed-independent
                c = self.table[f].get(s, 0)
                if c > 0:
                    pmi = math.log((c / self.ftot[f]) / (self.stot[s] / self.n))
                    if pmi > 0:                          # only distinctive associations promote
                        tot += pmi
            return tot

        return sorted(cands, key=lambda p: (-score(p), _size(p, basis)))

    def reinforce(self, examples: list[Example], prog: Program, *, weight: int = 3) -> None:
        self._learn(examples, _skeleton(prog), weight)


def guided_induce(name: str, examples: list[Example], basis: Basis | None = None,
                  guide: SearchGuide | None = None, *, holdout_frac: float = 0.4
                  ) -> tuple[Induced | None, int]:
    """induce() with learned candidate ordering. Returns (Induced|None, candidates_tried) —
    the tried-count is the MEASURED search-efficiency metric. Verify gate unchanged."""
    basis = basis or seed_basis()
    ex = list(examples)
    if len(ex) < 4:
        return None, 0
    k = max(2, int(len(ex) * (1 - holdout_frac)))
    train, held = ex[:k], ex[k:]
    ordered = guide.order(ex, basis) if guide else list(_candidates(basis))
    tried = 0
    fits: list[Program] = []
    for prog in ordered:
        tried += 1
        if all(prog.run(a, b, basis) == out for (a, b), out in train) \
                and held and all(prog.run(a, b, basis) == out for (a, b), out in held):
            fits.append(prog)
            break                       # guided mode: first verified hit (ordering encodes prior)
    if not fits:
        return None, tried
    best = fits[0]
    best.name = name
    fn = (lambda p: (lambda a, b: p.run(a, b, basis)))(best)
    ind = Induced(best, fn, len(train), len(held), sorted(basis.keys()))
    if guide:
        guide.reinforce(ex, best)
    record_induced(ind, tried=tried, guided=guide is not None)
    return ind, tried


# ---------------------------------------------------------------- prediction error → self-mod
def check_and_repair(ind: Induced, examples: list[Example], truth_fn: Callable[[int, int], int],
                     probes: list[tuple[int, int]], basis: Basis | None = None,
                     guide: SearchGuide | None = None) -> tuple[Induced, bool, list[Example]]:
    """Exercise a hypothesis against verified truth. On the first prediction error: receipt →
    counterexample joins the examples → RE-INDUCE → tombstone the old program. Returns
    (current_procedure, was_repaired, updated_examples). This IS the owner's flywheel: the rule
    acts in the world; the world's contradiction rewrites the structure, through the same gate."""
    basis = basis or seed_basis()
    for a, b in probes:
        expect = truth_fn(a, b)
        got = ind.fn(a, b)
        if got != expect:
            record_error(ind.program.name, ind.program, ((a, b), expect), expect, got)
            record_tombstone(ind.program.name, ind.program,
                             f"prediction_error at ({a},{b}): got {got}, truth {expect}")
            updated = examples + [((a, b), expect)]
            # counterexample must constrain BOTH phases: put it in train and duplicate to holdout
            repaired, _tried = guided_induce(ind.program.name, updated + [((a, b), expect)],
                                             basis, guide)
            if repaired is not None:
                return repaired, True, updated
            return ind, False, updated       # honest: no program fits yet — keep old + receipts
    return ind, False, examples


# ---------------------------------------------------------------- F1: sleep-abstraction
# Because our programs are DATA (init/count/op/arg), an induced executor can be persisted and
# rebuilt — the learned library SURVIVES restarts. sleep_abstraction() reads the ledger and
# auto-promotes verified induced programs into a persistent library; load_library() rebuilds a
# working basis from disk. Compositional towers become possible without any hand grow_basis:
# S (seed) → add → double → 2^a, each level induced on the levels below.
_LIBRARY = _ROOT / "data" / "reasoning" / "procedure_library.json"


def _load_lib_file() -> dict[str, dict[str, str]]:
    try:
        return json.loads(_LIBRARY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_lib_file(lib: dict[str, dict[str, str]]) -> None:
    _LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    _LIBRARY.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")


def sleep_abstraction() -> dict[str, Any]:
    """Sleep phase, automated: mine the hypothesis ledger for VERIFIED induced programs and
    promote them into the persistent library (skipping tombstoned versions). Returns a report.
    No hand grow_basis — the library grows itself from what induction earned."""
    lib = _load_lib_file()
    tombstoned: set[str] = set()
    promoted = 0
    try:
        rows = [json.loads(ln) for ln in _LEDGER.read_text(encoding="utf-8").splitlines()]
    except Exception:
        rows = []
    for r in rows:
        if r.get("kind") == "tombstone":
            tombstoned.add(f"{r.get('name')}::{r.get('program')}")
    for r in rows:
        if r.get("kind") != "induced" or int(r.get("verified_held_out") or 0) < 1:
            continue
        key = f"{r.get('name')}::{r.get('program')}"
        if key in tombstoned:
            continue                                   # errors are learned from, not re-promoted
        init, count, op, arg = str(r.get("skeleton")).split("/")
        lib[str(r.get("name"))] = {"init": init, "count": count, "op": op, "arg": arg}
        promoted += 1
    _save_lib_file(lib)
    return {"library_size": len(lib), "promoted_rows": promoted, "path": str(_LIBRARY)}


def load_library(base: Basis | None = None) -> Basis:
    """Rebuild a working basis from the persistent library. Programs may reference EACH OTHER
    (double built on add built on S) — resolved by iterating until all definable entries load.
    The learned executors outlive the process: induced once, callable forever."""
    basis: Basis = dict(base or seed_basis())
    lib = _load_lib_file()
    pending = dict(lib)
    for _ in range(len(pending) + 1):                  # dependency passes (towers are shallow)
        progressed = False
        for name, spec in list(pending.items()):
            if spec["op"] not in basis:
                continue                               # dependency not loaded yet
            prog = Program(spec["init"], spec["count"], spec["op"], spec["arg"], name=name)
            frozen = dict(basis)                       # bind the CURRENT basis for this fn
            basis[name] = ((lambda p, bs: (lambda a, b: p.run(a, b, bs)))(prog, frozen), 2)
            del pending[name]
            progressed = True
        if not progressed:
            break
    return basis
