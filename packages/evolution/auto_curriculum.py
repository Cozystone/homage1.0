# -*- coding: utf-8 -*-
"""Autonomous self-curriculum for the code evolver (owner 2026-07-13:
" ").

Until now the engine's capability jumped only when a HUMAN added a primitive: + - * // (v1),
conditionals (v3), fold/len (v4), map/filter (RSI-6). That hand-tuning is exactly what should NOT
be needed. This module makes the frontier advance on its own.

THE MECHANISM — self-generated, self-verified problems.
Code has a free exact oracle (the interpreter). So the engine can invent a problem it is able to
CHECK without any human answer key: take programs it has ALREADY solved (its library), compose them
with the safe interpreter into a new target, run that composite over sampled inputs to get the
reference outputs, then hide the composite and make the search RE-DERIVE it (with the library
available as building blocks). Every "answer key" is a real verified program actually run — nothing
is fabricated. A solved problem becomes a new building block, so the next round can compose deeper.
A curriculum controller raises difficulty automatically when the solve-rate stays high, and holds
when it collapses. No human writes targets, sets the schedule, or edits a primitive.

CAPABILITY = THE FUNCTION, NOT THE TREE (anti-bloat, honesty).
A naive compose-and-keep loop fills the library with ever-more-baroque monster expressions that
pass verification but teach nothing — fake progress. So the library is keyed by BEHAVIORAL
SIGNATURE (the tuple of outputs over a fixed probe battery), and it keeps the SMALLEST program per
signature. Two syntactically different trees that compute the same function collapse to one capability;
a shorter re-derivation of a known function counts as compression. "distinct_solved" therefore means
distinct FUNCTIONS the engine can compute — an honest measure — and generation is biased toward small
blocks with bounded arity so trees stay compact. Every acceptance still passes a held-out
generalization gate (the synthesize_verified discipline). Nothing is exec'd; trees are interpreted.

HONEST SCOPE: this accumulates COMPOSITIONAL DEPTH over a fixed axiom set — re-deriving and
remembering deeper, compact combinations of its primitives — which is genuine, measurable capability
growth. It does not conjure new mathematics from nothing.
"""
from __future__ import annotations

import itertools
import json
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Any

from packages.evolution import compression_progress as _cp
from packages.evolution import egraph_abstraction as _egraph
from packages.evolution import qd_archive as _qd
from packages.evolution.abstraction import instantiate as _instantiate
from packages.evolution.abstraction import match as _match
from packages.evolution.abstraction import mine as _mine_abstractions
from packages.evolution.code_evolver import evaluate, evolve, fitness, to_source

# ---------------------------------------------------------------------------
# Families: a problem "family" fixes the input signature so any two solved programs in it compose
# with a consistent env. Every solved tree is INT-valued over its family's env, so composing two of
# them with an arithmetic op is again a valid int-valued program in the same family.
# ---------------------------------------------------------------------------
_FAMILIES: dict[str, dict[str, Any]] = {
    "ab": {"vars_": ["a", "b"], "list_vars": (), "control_flow": True},
    "xs": {"vars_": [], "list_vars": ("xs",), "control_flow": False},
}

# A FIXED probe battery per family — the behavioral fingerprint of a program is its outputs here.
# Two trees with identical fingerprints compute the same function (up to these probes) and are the
# same capability; we keep the smallest. Deterministic, so signatures compare across rounds/runs.
_PROBES: dict[str, list[dict[str, Any]]] = {
    "ab": [{"a": a, "b": b} for a, b in
           [(0, 0), (1, 0), (0, 1), (2, 3), (3, 2), (5, 1), (1, 5), (4, 4), (7, 2), (2, 7), (6, 3), (9, 0)]],
    "xs": [{"xs": L} for L in
           [[], [0], [1], [2, 2], [1, 2, 3], [3, 1, 2], [4, 0, 4], [5, 5, 5, 5], [1, 2, 3, 4], [6, 1], [0, 0, 0], [2, 4, 6]]],
}


def _sample_env(family: str, rng: random.Random) -> dict[str, Any]:
    """Sample a random env for a family: an int in 0..9 per scalar var, then a length-1..6 list of ints
    0..7 per list var. Data-driven from _FAMILIES so new families need no special-casing; for the base
    families ('ab': a,b then 'xs': xs) the rng draw order is byte-identical to the original hardcoding."""
    fam = _FAMILIES[family]
    env: dict[str, Any] = {v: rng.randint(0, 9) for v in fam["vars_"]}
    for lv in fam["list_vars"]:
        n = rng.randint(1, 6)
        env[lv] = [rng.randint(0, 7) for _ in range(n)]
    return env


def signature(tree: Any, family: str) -> str:
    """The behavioral fingerprint: outputs over the fixed probe battery, joined to a stable string.
    This is the capability identity — what the program COMPUTES, independent of how it's written."""
    return ",".join(str(evaluate(tree, env)) for env in _PROBES[family])


def _size(tree: Any) -> int:
    """Node count — the parsimony measure. Smaller programs are preferred (compression = understanding)."""
    if not isinstance(tree, (tuple, list)):
        return 1
    if not tree:
        return 1
    return 1 + sum(_size(t) for t in tree[1:] if isinstance(t, (tuple, list)))


def _is_trivial(tree: Any, family: str) -> bool:
    """A program is a genuine capability only if it actually COMPUTES something. Reject the degenerate
    cases so the metric can't be inflated: a constant (same output for every probe) or a pure input
    projection (behaviorally identical to a bare input variable). len/sum/max etc. all survive."""
    outs = [evaluate(tree, env) for env in _PROBES[family]]
    if len(set(outs)) <= 1:
        return True                                          # constant — computes nothing
    for v in _FAMILIES[family]["vars_"]:
        if outs == [env[v] for env in _PROBES[family]]:
            return True                                      # identity projection — computes nothing
    return False


# Seed axioms — the small hand-given starting set. Everything past these is reached by composition,
# not by a human adding a primitive. Each seed is a compact canonical target the engine re-derives.
_SEED_TREES: dict[str, list[tuple[str, Any]]] = {
    "ab": [
        ("a+b", ("op", "+", ("var", "a"), ("var", "b"))),
        ("a*a+b", ("op", "+", ("op", "*", ("var", "a"), ("var", "a")), ("var", "b"))),
        ("max(a,b)", ("if", ("cmp", ">", ("var", "a"), ("var", "b")), ("var", "a"), ("var", "b"))),
    ],
    "xs": [
        ("sum(xs)", ("fold", "+", ("const", 0), "xs")),
        ("len(xs)", ("len", "xs")),
        ("sum_evens", ("fold", "+", ("const", 0),
                       ("filter", ("cmp", "==", ("op", "%", ("var", "_x"), ("const", 2)),
                                   ("const", 0)), "xs"))),
    ],
}

_LIB_CAP = 40            # bounded distinct functions per family
_MAX_KEEP_SIZE = 34      # reject a solution too bloated to be a clean building block
_UP, _DOWN = 0.7, 0.34   # competence thresholds: mastery raises / failure lowers the tier
_SATURATED = 0.2         # novelty below this (at mastery) means the tier is exhausted → climb
_FAST = 0.5              # novelty above this means we're learning fast → push ahead

# Close the invention->solver loop: feed gate-passing invented primitives to the SOLVER as building
# blocks (not only to problem-generation). This is the a-priori cap the self-acceleration measurement
# identified — an invented primitive could pose harder problems but never expand the solver's
# vocabulary. Default ON. The measurement harness flips this to reproduce the pre-closure (open-loop)
# baseline for an apples-to-apples curve-shape comparison.
_CLOSE_LOOP = True

# ---------------------------------------------------------------------------
# X1 — COMPRESSION-PROGRESS DRIVE (owner 2026-07-23; docs/ATANOR_intelligence_explosion_research.md).
# The prior target selection is a crude competence/novelty self-pacing heuristic: it composes ONE blind
# target per slot and paces difficulty by solve-rate. The research verdict is that the principled driver
# of open-ended self-acceleration is Schmidhuber's COMPRESSION-PROGRESS signal — pursue the target whose
# learning would most reduce future description-length, i.e. the learnable-but-not-yet-learned frontier.
# When ATANOR_COMPRESSION_DRIVE is set, target selection generates a POOL of candidates and picks the one
# with the highest expected compression progress (compression_progress.interestingness) instead of a
# blind single composition. DEFAULT OFF preserves the exact prior behaviour so the A/B is clean.
# ---------------------------------------------------------------------------
_POOL = 8                # candidate targets generated per slot when the drive is on (ranked, argmax kept)


def _drive_on() -> bool:
    """Read the ATANOR_COMPRESSION_DRIVE flag AT CALL TIME (so an A/B harness can flip it per arm in
    the same process). Off unless explicitly enabled — the baseline is byte-identical to the prior
    competence/novelty behaviour."""
    return os.getenv("ATANOR_COMPRESSION_DRIVE", "0").strip().lower() not in ("", "0", "false", "no", "off")


# ---------------------------------------------------------------------------
# X2 — TIER-OPENING (babble) ABSTRACTION MINER (owner 2026-07-23; docs/ATANOR_intelligence_explosion_
# research.md deficit-2 "multiplicative reuse"). The default miner (abstraction.mine) anti-unifies
# statement SYNTAX — an ADDITIVE lever (it factors exact repeats). It cannot see that `a + a*a` and
# `b*b + b` are the SAME motif (they differ by commutativity) so it never names the reusable function.
# When ATANOR_EGRAPH_ABSTRACTION is set, mining runs egraph_abstraction.mine instead: e-graph +
# equality saturation over the interpreter's OWN identities + anti-unification over e-classes, which
# finds tier-opening motifs modulo the equational theory. DEFAULT OFF (baseline unchanged). Composable
# with X1: the two flags are read independently, so X1+X2 = both set.
# ---------------------------------------------------------------------------
def _egraph_on() -> bool:
    """Read the ATANOR_EGRAPH_ABSTRACTION flag AT CALL TIME (independent of X1's drive flag, so the A/B
    harness can set X1-only vs X1+X2 in one process). Off unless explicitly enabled."""
    return os.getenv("ATANOR_EGRAPH_ABSTRACTION", "0").strip().lower() not in ("", "0", "false", "no", "off")


def _mine_for(library: list, *, top_k: int = 6, min_gain: int = 2) -> list[dict]:
    """Dispatch to the tier-opening e-graph miner (X2) when its flag is on, else the naive syntactic
    miner. Both return the SAME {template, arity, gain, source} record shape, and the mined templates
    pass through the identical downstream non-degeneracy gate (`_expands_reachable` in
    `_solver_primitives`) before any primitive enters the solver vocabulary — so X2 changes WHICH
    motifs are proposed, never RELAXES the semantic admission gate."""
    miner = _egraph.mine if _egraph_on() else _mine_abstractions
    return miner(library, top_k=top_k, min_gain=min_gain)


# ---------------------------------------------------------------------------
# X3 — MAP-ELITES / QD DIVERGENT ARCHIVE (owner 2026-07-23; docs/ATANOR_intelligence_explosion_
# research.md deficit-1 "발산 아카이브"). X2 proved the multiplicative miner works but ④ PLATEAUED
# because the archive is CONVERGENT (smallest-program-per-signature): tier-opening abstractions were
# alternative spellings of already-reachable functions — search noise, no leverage. X3 replaces the
# convergent library with a DIVERGENT one: an elite per behavioural-structural NICHE (qd_archive), so
# diverse stepping stones accumulate. The richer library is what compose_target recombines AND what the
# miner anti-unifies — the two channels through which divergence compounds into NEW reachable regions.
# When ATANOR_QD_ARCHIVE is set: the building-block library the solver / composer / miner sees becomes
# the archive's elite set (a superset of the convergent per-signature library). The honest metric is
# unchanged — distinct_solved still counts distinct FUNCTIONS (signatures), never niches. DEFAULT OFF
# (baseline byte-identical). Read independently of X1/X2, so all three compose.
# ---------------------------------------------------------------------------
_QD_CAP = 48             # bounded niches per family (divergent stepping stones), above _LIB_CAP but lean


def _qd_on() -> bool:
    """Read the ATANOR_QD_ARCHIVE flag AT CALL TIME (independent of X1's drive and X2's e-graph flags, so
    the A/B harness can set X1 / X1+X2 / X1+X2+X3 in one process). Off unless explicitly enabled."""
    return os.getenv("ATANOR_QD_ARCHIVE", "0").strip().lower() not in ("", "0", "false", "no", "off")


def _qd_channels() -> set:
    """Which channels the divergent archive feeds (ATANOR_QD_CHANNELS, default 'mine'). Isolating the
    channels is load-bearing for an HONEST verdict: measurement showed that routing compose/solve through
    the archive DILUTES the clean convergent compositional substrate and makes the verified frontier
    WORSE, while the archive's real value is giving X2's MINER diverse subtrees to anti-unify (the
    diagnosed 'multiplicative reuse needs diverse stepping stones' bottleneck). Channels:
      'mine'    — the miner anti-unifies over the divergent archive (default; where diversity pays);
      'compose' — compose_target recombines archive elites (measured dilutive);
      'solve'   — the solver's building-block library is the archive (measured dilutive).
    'all' = mine+compose+solve. The archive is ALWAYS maintained + harvested when _qd_on (so divergence is
    measurable regardless of channels); channels only gate where it is CONSUMED."""
    raw = os.getenv("ATANOR_QD_CHANNELS", "mine").strip().lower()
    if raw in ("all", "*"):
        return {"mine", "compose", "solve"}
    return {c.strip() for c in raw.split(",") if c.strip()} or {"mine"}


def _qd_library(state: dict[str, Any], family: str) -> list:
    """The DIVERGENT building-block library when X3 is on: the MAP-Elites elite set (diverse stepping
    stones), deterministically ordered. This is what the solver, compose_target and the miner see."""
    return _qd.elites(state.get("niches", {}).get(family, {}))


def _qd_record(state: dict[str, Any], family: str, tree: Any) -> str:
    """Insert an accepted, non-trivial, non-bloated program into the family's MAP-Elites archive. Applies
    the SAME parsimony/non-triviality gates as `_admit` (so the archive is a clean superset of the
    convergent one) but NOT the per-signature collapse — structurally-distinct spellings get their own
    niches. Returns the qd_archive verdict ('new_niche'/'elite_improved'/'kept'/'reject')."""
    if _size(tree) > _MAX_KEEP_SIZE or _is_trivial(tree, family):
        return "reject"
    arch = state.setdefault("niches", {}).setdefault(family, {})
    sig = signature(tree, family)
    return _qd.insert(arch, tree, sig, _size(tree), to_source(tree), cap=_QD_CAP)


def _select_target(library: list[Any], family: str, tier: int, rng: random.Random,
                   abstractions: tuple, state: dict[str, Any], *, pool: int = _POOL) -> Any:
    """Compression-progress target selection (X1). Generate `pool` candidate targets (the same
    compose_target the baseline uses) and return the one with the highest expected compression progress
    — the learnable-but-not-yet-learned frontier — rather than a single blind composition. A candidate
    whose behavioural signature is ALREADY known scores 0 (re-learning a solved function yields no
    progress: the not-yet-learned half of the drive). Falls back to a blind composition if nothing
    scores. This is the ONLY behavioural change vs the baseline, and only when the flag is on."""
    known = set(state["sigs"].get(family, ()))
    best_t: Any = None
    best_s = -1.0
    for _ in range(max(1, pool)):
        cand = compose_target(library, family, tier, rng, abstractions=abstractions)
        try:
            score = _cp.interestingness({"tree": cand, "family": family}, state)
        except Exception:
            score = 0.0
        try:
            if signature(cand, family) in known:
                score = 0.0                                  # already learned -> zero compression progress
        except Exception:
            pass
        if score > best_s:
            best_s, best_t = score, cand
    if best_t is None:
        return compose_target(library, family, tier, rng, abstractions=abstractions)
    return best_t


def _tests_from_tree(tree: Any, family: str, n: int, rng: random.Random
                     ) -> list[tuple[dict[str, Any], int]]:
    """Turn a (verified) target tree into input→output examples by running it — the honest answer key."""
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 6:
        tries += 1
        env = _sample_env(family, rng)
        key = json.dumps(env, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append((env, evaluate(tree, env)))
    return out


def compose_target(library: list[Any], family: str, tier: int, rng: random.Random,
                   abstractions: tuple = ()) -> Any:
    """Invent a NEW target by combining solved building blocks with the safe interpreter. Operands are
    biased toward SMALL blocks and arity is bounded, so targets stay compact (no monster bloat). Higher
    tiers allow one more operand and (for 'ab') a conditional wrap — difficulty grows structurally.
    When the engine has INVENTED primitives (mined abstractions), it sometimes builds the target from
    one — instantiating the motif on fresh operands — so its own inventions drive the next problems."""
    from packages.evolution.code_evolver import _OPS, _CMP  # local: whitelisted primitive names

    fam = _FAMILIES[family]
    blocks = sorted(library, key=_size)                      # prefer the compact, canonical blocks
    small = blocks[: max(3, len(blocks) // 2 + 1)] or blocks
    leaves = [("var", v) for v in fam["vars_"]] + [("const", rng.randint(1, 3))]

    def pick() -> Any:
        if small and rng.random() < 0.7:
            return rng.choice(small)
        return rng.choice(leaves) if leaves else rng.choice(small or [("const", 1)])

    # seed the target from an INVENTED primitive — the engine building on its own abstractions.
    if abstractions and rng.random() < 0.4:
        ab = rng.choice(abstractions)
        node = _instantiate(ab["template"], [pick() for _ in range(ab["arity"])])
        if tier >= 1 and rng.random() < 0.5:
            node = ("op", rng.choice(list(_OPS)), node, pick())
        return node

    arity = 2 if tier < 2 else rng.choice([2, 2, 3])
    node = pick()
    for _ in range(arity - 1):
        node = ("op", rng.choice(list(_OPS)), node, pick())
    if fam["control_flow"] and len(fam["vars_"]) >= 2 and tier >= 1 and rng.random() < 0.3:
        v0, v1 = fam["vars_"][0], fam["vars_"][1]
        node = ("if", ("cmp", rng.choice(list(_CMP)), ("var", v0), ("var", v1)), node, pick())
    return node


# ---------------------------------------------------------------------------
# State: libraries[fam] = trees, aligned with programs[fam] = sources and sigs[fam] = fingerprints.
# Dedup by signature keeps the smallest tree per FUNCTION — the library is a set of capabilities.
# ---------------------------------------------------------------------------
def new_state() -> dict[str, Any]:
    return {"round": 0, "tier": 0,
            "libraries": {f: [] for f in _FAMILIES},
            "programs": {f: [] for f in _FAMILIES},
            "sigs": {f: [] for f in _FAMILIES},
            "abstractions": {f: [] for f in _FAMILIES},   # invented primitives (mined motifs)
            "niches": {f: {} for f in _FAMILIES},          # X3 MAP-Elites archive (elite per niche)
            "history": [],
            "frontier": {"distinct_solved": 0, "compressions": 0, "avg_size": 0.0,
                         "invented_primitives": 0}}


def _admit(state: dict[str, Any], family: str, tree: Any) -> str:
    """Add a capability by behavioral signature. Returns 'new' (a function not seen before),
    'compressed' (a shorter program for a known function), or 'dup'/'reject'."""
    if _size(tree) > _MAX_KEEP_SIZE or _is_trivial(tree, family):
        return "reject"
    sig = signature(tree, family)
    sigs = state["sigs"][family]
    src = to_source(tree)
    if sig not in sigs:
        if len(sigs) >= _LIB_CAP:
            return "reject"
        state["libraries"][family].append(tree)
        state["programs"][family].append(src)
        sigs.append(sig)
        return "new"
    i = sigs.index(sig)
    if _size(tree) < _size(state["libraries"][family][i]):
        state["libraries"][family][i] = tree                 # compression: keep the shorter program
        state["programs"][family][i] = src
        return "compressed"
    return "dup"


# ---------------------------------------------------------------------------
# NON-DEGENERACY GATE for invented primitives entering the SOLVER vocabulary (owner 2026-07-22).
# abstraction.mine() already enforces parsimony (body >= 2), 1-2 holes, no pinned body-variable,
# well-formedness, compression gain and source-dedup. That is necessary but NOT sufficient to let a
# primitive expand the SOLVER: a template can compress the library yet be SEMANTICALLY degenerate —
# e.g. λx0. len(map(_x->x0, xs)) == len(xs) (the map body never affects a length), which pollutes the
# vocabulary with a fake parameter. Before a primitive may be built with, it must pass a semantic
# 'expands reachable functions' test on top of the syntactic gates above.
# ---------------------------------------------------------------------------
def _hole_arg_pool(family: str) -> list[Any]:
    """Concrete int-valued argument subtrees for PROBING an invented template's hole-sensitivity: the
    family's own variables and list reductions, plus two small constants. All int-valued, so binding a
    (well-formed) template's holes to them always yields a tree the interpreter can score."""
    fam = _FAMILIES[family]
    pool: list[Any] = [("var", v) for v in fam["vars_"]]
    for lv in fam["list_vars"]:
        pool.append(("len", lv))
        pool.append(("fold", "+", ("const", 0), lv))
    pool += [("const", 1), ("const", 2)]
    return pool


def _atomic_signatures(family: str) -> set:
    """Behavioral signatures of the family's ATOMS — its seed axioms and bare leaves (each variable,
    len(list), sum(list)). A primitive whose every non-trivial behavior reproduces one of these
    computes nothing the engine cannot already reach in a single step, so it expands nothing."""
    atoms: list[Any] = [t for _n, t in _SEED_TREES[family]]
    for v in _FAMILIES[family]["vars_"]:
        atoms.append(("var", v))
    for lv in _FAMILIES[family]["list_vars"]:
        atoms.append(("len", lv))
        atoms.append(("fold", "+", ("const", 0), lv))
    sigs: set = set()
    for a in atoms:
        try:
            sigs.add(signature(a, family))
        except Exception:
            pass
    return sigs


def _expands_reachable(template: Any, arity: int, family: str) -> bool:
    """The semantic gate an invented primitive must pass before it may enter the SOLVER vocabulary.
    Two required tests:
      (G1) HOLE-SENSITIVITY — the template's output must genuinely DEPEND on its hole arguments. A
           template that yields one identical signature across every probe binding has a vestigial
           parameter (len(map(_x->x0, xs)) == len(xs): the map body cannot change a length) and is a
           fake function of its argument → reject.
      (G2) REACHABILITY EXPANSION — at least one NON-TRIVIAL behavior it produces must not already be
           an atom/seed signature. This rejects algebraic identities that collapse to an existing
           primitive (x0 + 0 == x0). A primitive earns solver status only if it can reach a genuinely
           new function, not merely rename one the engine already computes."""
    if arity < 1:
        return False
    pool = _hole_arg_pool(family)
    if not pool:
        return False
    combos = list(itertools.product(pool, repeat=arity))[:16]
    all_sigs: set = set()
    nontrivial: set = set()
    for combo in combos:
        inst = _instantiate(template, list(combo))
        try:
            s = signature(inst, family)
        except Exception:
            continue
        all_sigs.add(s)
        if not _is_trivial(inst, family):
            nontrivial.add(s)
    if len(all_sigs) < 2:                                   # G1: output invariant to holes → vestigial
        return False
    if not nontrivial:                                     # only constants / identity projections
        return False
    if nontrivial.issubset(_atomic_signatures(family)):    # G2: never reaches beyond existing atoms
        return False
    return True


def _solver_primitives(state: dict[str, Any], family: str) -> tuple:
    """Gate-passed invented primitives offered to the solver as building blocks. Filters the mined
    abstractions (already parsimony/compression/dedup-gated) through the semantic non-degeneracy gate,
    so only primitives that actually expand the reachable function space enter the vocabulary."""
    out: list[dict[str, Any]] = []
    seen: set = set()
    for ab in state["abstractions"].get(family, ()):
        key = ab.get("source")
        if key in seen:
            continue
        tmpl, ar = ab.get("template"), int(ab.get("arity", 0))
        if not _expands_reachable(tmpl, ar, family):
            continue
        seen.add(key)
        out.append({"template": tmpl, "arity": ar})
    return tuple(out)


def _uses_primitive(tree: Any, primitives: tuple) -> bool:
    """Provenance: did the accepted solution actually BUILD with an invented primitive? True when any
    subtree is a structural instance of a primitive's template (its non-hole skeleton). abstraction.mine
    guarantees each template has non-hole body >= 2, so a match means the primitive's structure is
    genuinely present, not a spurious tiny-pattern hit."""
    if tree is None or not primitives:
        return False
    stack = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, (tuple, list)) and node:
            for prim in primitives:
                if _match(prim["template"], node, {}) is not None:
                    return True
            for c in node[1:]:
                if isinstance(c, (tuple, list)):
                    stack.append(c)
    return False


_HARVEST_CAP = 12        # X3: max distinct stepping stones harvested from one search's final population


def _solve_and_gate(target: Any, family: str, tier: int, library: list[Any],
                    rng: random.Random, primitives: tuple = (), harvest: bool = False) -> dict[str, Any]:
    """Solve a generated target on TRAIN and require it to pass a fresh HOLDOUT (generalization) before
    it may enter the library — the synthesize_verified discipline, so the library stays clean. When
    `primitives` is supplied (the closed invention->solver loop), the search may BUILD with the engine's
    own gate-passed invented primitives, not only recombine solved whole programs.

    `harvest` (X3): also return `stepping_stones` — the DISTINCT, NON-TRIVIAL programs the search revealed
    in its final population. These are NOT claimed as solved capabilities (distinct_solved stays verified-
    only); they are extra reusable building blocks (each computes a real, total function) that the QD
    archive keeps as diverse stepping stones — the MAP-Elites illumination of the search."""
    fam = _FAMILIES[family]
    train = _tests_from_tree(target, family, 14, rng)
    holdout = _tests_from_tree(target, family, 10, rng)
    budget = 90 + 30 * tier
    res = evolve(train, fam["vars_"], list_vars=fam["list_vars"],
                 control_flow=fam["control_flow"], library=tuple(library), primitives=primitives,
                 pop=110, generations=min(budget, 240), rng_seed=rng.randint(1, 10_000),
                 return_population=harvest)
    tree = res.get("tree")
    hold = fitness(tree, holdout) if tree else 0.0
    accepted = bool(res["solved"] and hold >= 1.0)
    out = {"accepted": accepted, "solved": res["solved"], "holdout": round(hold, 3),
           "program": res["program"], "tree": tree, "target": to_source(target),
           "used_primitive": _uses_primitive(tree, primitives) if accepted else False}
    if harvest:
        out["stepping_stones"] = _harvest_stones(res.get("population", ()), family, train)
    return out


def _harvest_stones(population: Any, family: str, train: list) -> list[Any]:
    """The COMPETENT, distinct stepping stones a search revealed — MAP-Elites illumination with a QUALITY
    floor. A naive dump of the whole final population floods the archive with near-random programs that
    DILUTE composition (measured: it made the verified frontier worse). So keep only population members
    that are genuinely COMPETENT on the target (exact on TRAIN) — real alternative solutions / structural
    variants of a real function, not junk — deduplicated by source, ranked competence-then-parsimony, and
    capped so one search cannot flood the archive. Trivial and oversize trees are dropped."""
    scored: list[tuple] = []
    seen: set = set()
    for t in population:
        if not isinstance(t, (tuple, list)) or not t:
            continue
        if _size(t) > _MAX_KEEP_SIZE or _is_trivial(t, family):
            continue
        f = fitness(t, train)
        if f < 1.0:                                      # QUALITY floor: only exact solvers of the target
            continue
        src = to_source(t)
        if src in seen:
            continue
        seen.add(src)
        scored.append((-f, _size(t), src, t))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))        # competence desc, then parsimony, then stable
    return [t for _f, _s, _src, t in scored[:_HARVEST_CAP]]


def autonomous_round(state: dict[str, Any], rng: random.Random, *, problems: int = 6) -> dict[str, Any]:
    """One self-driven round: bootstrap missing seeds, then generate + solve composed problems, admit
    the generalizers by signature, and let the controller move the tier. Mutates and returns state."""
    state["round"] += 1
    tier = state["tier"]
    attempts, solved_ok, admitted, compressed, details = 0, 0, 0, 0, []
    solver_prim_uses = 0
    qd = _qd_on()                                        # X3: maintain + harvest the divergent archive
    chans = _qd_channels() if qd else set()              # which channels CONSUME it (default: mine only)

    for family in _FAMILIES:
        conv_lib = state["libraries"][family]
        # X3 channel routing. The archive is always maintained/harvested when qd, but each CONSUMER
        # (compose_target, the solver, the miner) draws from the divergent archive only if its channel is
        # enabled — else from the clean convergent per-signature library. Measurement drives the default
        # (compose/solve dilute; mining is where diverse stepping stones pay). Recomputed live so
        # within-round admissions/harvests are immediately available (parity with the baseline grow).
        _compose_lib = ((lambda f=family: _qd_library(state, f)) if (qd and "compose" in chans)
                        else (lambda l=conv_lib: l))
        _solve_lib = ((lambda f=family: _qd_library(state, f)) if (qd and "solve" in chans)
                      else (lambda l=conv_lib: l))
        abns = tuple(state["abstractions"].get(family, ()))
        # CLOSE THE INVENTION->SOLVER LOOP: the gate-passing invented primitives become SOLVER building
        # blocks (not only problem seeds). _solver_primitives applies the non-degeneracy gate so only
        # primitives that genuinely expand the reachable function space enter the search vocabulary.
        solver_prims = _solver_primitives(state, family) if _CLOSE_LOOP else ()
        # (1) bootstrap the family's compact seed axioms before composing.
        for name, tree in _SEED_TREES[family]:
            if signature(tree, family) in state["sigs"][family]:
                continue
            attempts += 1
            g = _solve_and_gate(tree, family, tier, _solve_lib(), rng, primitives=solver_prims, harvest=qd)
            if g["accepted"]:
                solved_ok += 1
                verdict = _admit(state, family, g["tree"])
                if qd:
                    _qd_record(state, family, g["tree"])
                admitted += verdict == "new"
                compressed += verdict == "compressed"
                solver_prim_uses += bool(g.get("used_primitive"))
            if qd:                                       # X3: harvest diverse stepping stones (illumination)
                for st in g.get("stepping_stones", ()):
                    _qd_record(state, family, st)
            details.append({"family": family, "kind": "seed", "name": name,
                            "used_primitive": bool(g.get("used_primitive")), **_slim(g)})

        # (2) compose: invent new targets from what's solved, re-derive them, keep the generalizers.
        # The engine's own INVENTED primitives (mined motifs) seed some of these targets AND — with the
        # loop closed — are available to the solver to re-derive them.
        per_family = max(1, problems // len(_FAMILIES))
        for _ in range(per_family):
            if not _compose_lib():
                break
            # X1: compression-progress selection when the drive is on, else the baseline blind compose.
            if _drive_on():
                target = _select_target(_compose_lib(), family, tier, rng, abns, state)
            else:
                target = compose_target(_compose_lib(), family, tier, rng, abstractions=abns)
            attempts += 1
            g = _solve_and_gate(target, family, tier, _solve_lib(), rng, primitives=solver_prims, harvest=qd)
            verdict = "reject"
            if g["accepted"]:
                solved_ok += 1
                verdict = _admit(state, family, g["tree"])
                if qd:
                    _qd_record(state, family, g["tree"])
                admitted += verdict == "new"
                compressed += verdict == "compressed"
                solver_prim_uses += bool(g.get("used_primitive"))
            if qd:                                       # X3: harvest diverse stepping stones (illumination)
                for st in g.get("stepping_stones", ()):
                    _qd_record(state, family, st)
            details.append({"family": family, "kind": "composed", "verdict": verdict,
                            "size": _size(g["tree"]) if g["tree"] else 0,
                            "used_primitive": bool(g.get("used_primitive")), **_slim(g)})

    # (3) INVENT PRIMITIVES: mine recurring motifs from each family library into parameterized
    # abstractions (anti-unification), so the engine expands its own building-block vocabulary — not
    # just composition depth over a fixed axiom set, but new named primitives it discovered for itself.
    invented = 0
    for family in _FAMILIES:
        # X3: mine from the DIVERGENT archive (diverse stepping stones) when the 'mine' channel is on —
        # the channel through which X2's multiplicative reuse compounds: more diverse subtrees to
        # anti-unify. This is the default channel (measurement: where diversity pays without diluting).
        mine_lib = _qd_library(state, family) if (qd and "mine" in chans) else state["libraries"][family]
        found = _mine_for(mine_lib, top_k=6, min_gain=2)   # X2 e-graph miner if flagged
        state["abstractions"][family] = [
            {"template": a["template"], "arity": a["arity"], "source": a["source"], "gain": a["gain"]}
            for a in found]
        invented += len(found)

    # Two DIFFERENT signals drive the controller (the earlier single "solve-rate" was backwards —
    # novelty falls as a tier is exhausted, which must trigger a CLIMB, not a stall):
    #   competence = fraction of self-generated targets the engine actually solves+generalizes
    #   novelty    = fraction that were NEW functions (still learning at this tier)
    competence = (solved_ok / attempts) if attempts else 0.0
    novelty = (admitted / attempts) if attempts else 0.0
    moved = "hold"
    if competence >= _UP and novelty < _SATURATED:
        state["tier"] = min(tier + 1, 6)                     # MASTERED + saturated → harder targets
        moved = "up" if state["tier"] != tier else "hold"
    elif novelty >= _FAST:
        state["tier"] = min(tier + 1, 6)                     # learning fast → push ahead
        moved = "up" if state["tier"] != tier else "hold"
    elif competence < _DOWN and tier > 0:
        state["tier"] = tier - 1                             # can't solve its own targets → ease off
        moved = "down"

    distinct = sum(len(s) for s in state["sigs"].values())
    sizes = [_size(t) for f in _FAMILIES for t in state["libraries"][f]]
    state["frontier"] = {"distinct_solved": distinct,
                         "compressions": state["frontier"].get("compressions", 0) + compressed,
                         "avg_size": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                         "invented_primitives": invented}
    if qd:
        # X3 divergence report: niches (diverse stepping stones) vs distinct FUNCTIONS. The gap is the
        # divergence the convergent archive discards. distinct_solved above stays function-count honest.
        state["frontier"]["qd_niches"] = sum(len(state["niches"].get(f, {})) for f in _FAMILIES)
        state["frontier"]["qd_structural_variants"] = state["frontier"]["qd_niches"] - distinct
    rec = {"round": state["round"], "tier_before": tier, "tier_after": state["tier"], "move": moved,
           "attempts": attempts, "admitted": admitted, "compressed": compressed,
           "competence": round(competence, 3), "novelty": round(novelty, 3),
           "solver_prim_uses": solver_prim_uses, "drive": _drive_on(),
           "frontier": dict(state["frontier"]), "details": details, "ts": time.time()}
    state["history"].append({k: rec[k] for k in ("round", "tier_after", "competence", "novelty", "admitted")})
    state["history"] = state["history"][-200:]
    return rec


def _slim(g: dict[str, Any]) -> dict[str, Any]:
    return {"accepted": g["accepted"], "solved": g["solved"], "holdout": g["holdout"],
            "program": g["program"], "target": g["target"]}


def _arity(tree: Any) -> int:
    """How many primitive combinators the tree chains — a cheap structural difficulty proxy."""
    if not isinstance(tree, tuple):
        return 0
    if tree[0] in ("op", "if"):
        return 1 + sum(_arity(t) for t in tree[1:] if isinstance(t, tuple))
    return 0


# ---------------------------------------------------------------------------
# Persistence + bounded daemon
# ---------------------------------------------------------------------------
def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
            base = new_state()
            for k in ("round", "tier"):
                base[k] = s.get(k, base[k])
            for f in _FAMILIES:
                base["libraries"][f] = [_as_tree(t) for t in s.get("libraries", {}).get(f, [])]
                base["programs"][f] = list(s.get("programs", {}).get(f, []))
                base["sigs"][f] = list(s.get("sigs", {}).get(f, []))
                base["abstractions"][f] = [{**a, "template": _as_tree(a.get("template"))}
                                           for a in s.get("abstractions", {}).get(f, [])]
                base["niches"][f] = _qd.restore(s.get("niches", {}).get(f, {}))   # X3 archive round-trip
            base["history"] = s.get("history", [])
            base["frontier"] = s.get("frontier", base["frontier"])
            return base
        except Exception:
            pass
    return new_state()


def _as_tree(t: Any) -> Any:
    """JSON round-trips tuples to lists; the interpreter matches on tuples, so restore them."""
    if isinstance(t, list):
        return tuple(_as_tree(x) for x in t)
    return t


def _atomic_write_text(path: Path, text: str) -> None:
    """Crash-safe write: serialize to a sibling temp file, flush+fsync it, then os.replace onto the
    target (atomic on POSIX and Windows, same volume). A power loss mid-write leaves EITHER the old
    file intact OR the new one complete — never a half-written, corrupt file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_state(path: Path, state: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(state, ensure_ascii=False))


def run(rounds: int = 8, *, state_path: Path | None = None, journal_path: Path | None = None,
        seed: int | None = None, problems: int = 6, log=None) -> dict[str, Any]:
    """Run N self-curriculum rounds, persisting library + tier + a per-round journal so the owner can
    watch capability accrue WITHOUT touching code. Single-writer (this is the only mutator of state)."""
    state_path = state_path or _default_state_path()
    journal_path = journal_path or state_path.with_name("curriculum_journal.jsonl")
    state = load_state(state_path)
    rng = random.Random(seed if seed is not None else (state["round"] * 1009 + int(time.time()) % 9973))
    for _ in range(rounds):
        rec = autonomous_round(state, rng, problems=problems)
        save_state(state_path, state)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if log:
            log(f"[curriculum r{rec['round']}] tier {rec['tier_before']}→{rec['tier_after']} "
                f"({rec['move']}) new {rec['admitted']} + compressed {rec['compressed']} / {rec['attempts']} "
                f"competence={rec['competence']} novelty={rec['novelty']} frontier={rec['frontier']}")
    return {"round": state["round"], "tier": state["tier"], "frontier": state["frontier"],
            "distinct_solved": state["frontier"]["distinct_solved"],
            "libraries": {f: state["programs"][f] for f in _FAMILIES}}


def _default_state_path() -> Path:
    # runtime/, never the source tree — this is generated state, not code.
    return Path(__file__).resolve().parents[2] / "runtime" / "evolution" / "curriculum_state.json"
