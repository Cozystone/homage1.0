# -*- coding: utf-8 -*-
"""H4 — SCHEME SPACE: the mechanical substrate the generative proposer recombines over.

WHY THIS FILE EXISTS (the H4 question)
--------------------------------------
X4.4/X4.5 crossed the depth wall for a FIXED, HAND-WRITTEN set of synthesis recipes (identity-fold,
a HARDCODED k=2 pair-accumulator projection, direct composition). The recipes themselves were authored
by a human; the engine only SELECTED among them. H4 (Switch 2 v1 — the generative bridge in
docs/ATANOR_meta_diagnosis_loop.md and packages/meta_diagnosis/meta_diagnose.propose_novel_module,
which is a NotImplementedError stub) is the piece that has never been built: when the CURRENT recipe
vocabulary hits a WALL, INVENT a NEW recipe/scheme to cross it — not retrieve a known one.

This module is the SUBSTRATE, not the proposer. It provides:

  * a GENERALISATION of X4.5's hardcoded k=2 projection fold to an ARBITRARY-k accumulator whose
    auxiliary components are a GROWING BASIS of running-aggregate steps (not a fixed generic menu), and
  * the two structural MOVES the proposer recombines with — LIFT (turn a meta-basis binary op into a
    running-fold auxiliary) and GROW (append an auxiliary and put the output on the new top component),
    plus the PROMOTION generalisation (relativise a verified output-step so it becomes a reusable
    auxiliary at ANY index — the single "next order statistic" primitive that, invented once at k=2,
    is what every higher-k wall composes toward).

Everything is VERIFICATION-ANCHORED exactly like X4.4/X4.5: an assembled scheme is only ever accepted
after RE-EXECUTION reproduces the held-out I/O (`od.fitness(prog, verify) >= 1.0`). A scheme the
proposer dreams up that does not crack the real wall is discarded — the no-fabrication gate.

REUSE (no second implementation): the interpreter, `fold_s`/`unit`/`get`, `oe_enumerate` (Lever C
bottom-up observational-equivalence enumeration), `_proj_step_leaves`, `to_source`, `fitness`, and the
`_A`/`_E` scheme variables all come from `packages.evolution.open_domain` + `scheme_synthesis`. This
file adds the arbitrary-k assembly + deduction + the promotion-relativisation the proposer needs.

SAFETY. Pure interpretation over int|str|tuple; no exec/eval. The assembled programs are ordinary
`fold_s` trees the bounded interpreter already guarantees terminating.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from packages.evolution import open_domain as od
from packages.evolution import scheme_synthesis as ss

_A, _E = ss._A, ss._E                 # the scheme accumulator / element variables (reused)
CLAMP = od._INT_CLAMP
_REL = "get_rel"                      # position-relative accumulator read (template form, never interpreted)


# ============================================================================================
# POSITION-RELATIVE step templates — the promotion representation. A verified output step reads
# absolute accumulator components get(_a, j); to REUSE it as an auxiliary at a different index we
# rewrite every read RELATIVE to the step's own output index (get_rel(j - out_index)) and later
# INSTANTIATE it at whatever index the new chain needs. This is the mechanical core of "an invented
# scheme becomes a building block for the next" — the compounding channel.
# ============================================================================================
def _g(idx: int) -> tuple:
    """Absolute accumulator read: get(_a, idx)."""
    return ("get", ("var", _A), ("int", idx))


def relativize(step: Any, out_index: int) -> Any:
    """Rewrite a concrete step tree so every get(_a, j) becomes ('get_rel', j - out_index). _e and
    constants are left untouched. The result is an INDEX-FREE template reusable at any position."""
    if not isinstance(step, tuple) or not step:
        return step
    if step[:1] == ("get",) and len(step) == 3 and step[1] == ("var", _A) and step[2][:1] == ("int",):
        return (_REL, step[2][1] - out_index)
    return tuple([step[0]] + [relativize(c, out_index) if isinstance(c, tuple) else c for c in step[1:]])


def instantiate_rel(tmpl: Any, at_index: int) -> Any:
    """Instantiate a position-relative template at absolute index `at_index`: ('get_rel', d) ->
    get(_a, at_index + d). Inverse of `relativize`."""
    if not isinstance(tmpl, tuple) or not tmpl:
        return tmpl
    if tmpl[:1] == (_REL,) and len(tmpl) == 2:
        return _g(at_index + tmpl[1])
    return tuple([tmpl[0]] + [instantiate_rel(c, at_index) if isinstance(c, tuple) else c for c in tmpl[1:]])


# ============================================================================================
# THE AUXILIARY BASIS — each auxiliary is a running-aggregate whose UPDATE is a position-relative
# template + an init value + a generic PROTOTYPE (its running value as a plain function, used only for
# ranking / trajectory sanity, never returned as the program). `provenance` records LIFT (generic, from
# a meta-basis op) vs INVENTED (a promoted output-step). This is the vocabulary H4 grows.
# ============================================================================================
@dataclass(frozen=True)
class Aux:
    name: str
    template: Any                      # position-relative step template (get_rel form)
    init: int
    provenance: str                    # "lift:<op>"  |  "invented@<wall>"

    def step_at(self, idx: int) -> Any:
        return instantiate_rel(self.template, idx)


# LIFT MOVE — a meta-basis binary op becomes a running auxiliary reading its own previous value + _e.
# These are the base vocabulary the engine starts with (they are not hand-written RECIPES — they are the
# fundamental fold of a single meta-basis primitive, the same substrate X4.3/X4.5 already expose).
def lift(op: str) -> Aux:
    if op == "cnt":                                        # running count: add 1 each element
        return Aux("running_cnt", ("add", (_REL, 0), ("int", 1)), 0, "lift:cnt")
    init = {"max2": -CLAMP, "min2": CLAMP, "add": 0, "mul": 1}[op]
    name = {"max2": "running_max", "min2": "running_min", "add": "running_sum", "mul": "running_prod"}[op]
    return Aux(name, (op, (_REL, 0), ("var", _E)), init, f"lift:{op}")


def base_aux_basis() -> list[Aux]:
    """The starting auxiliary vocabulary: one running aggregate per meta-basis binary op (the LIFT move
    applied to the fundamental ops). NO order-statistic auxiliary is present — those must be INVENTED."""
    return [lift("max2"), lift("min2"), lift("add"), lift("mul"), lift("cnt")]


# ============================================================================================
# ARBITRARY-k ASSEMBLY — build the fold `step` / `init` from an ordered aux chain + the output step.
# The chain occupies accumulator indices 0..k-2; the output is index k-1. (X4.5's k=2 special case:
# aux_steps=[running_max], out at 1.)
# ============================================================================================
def build_step(aux_steps: list[Any], out_step: Any) -> Any:
    """Right-nested cat of unit(component-step): the k-tuple constructor the fold accumulator needs."""
    steps = list(aux_steps) + [out_step]
    node = ("unit", steps[-1])
    for s in reversed(steps[:-1]):
        node = ("cat", ("unit", s), node)
    return node


def build_init(aux_inits: list[int], out_init: int) -> Any:
    vals = list(aux_inits) + [out_init]
    node = ("unit", ("int", vals[-1]))
    for v in reversed(vals[:-1]):
        node = ("cat", ("unit", ("int", v)), node)
    return node


def assemble_projection(aux_chain: list[Aux], out_step: Any, out_init: int, listvar: str) -> Any:
    """Assemble  get(fold_s(step, init, xs), out_index)  for a projection-chain scheme."""
    k = len(aux_chain) + 1
    out_index = k - 1
    aux_steps = [aux_chain[i].step_at(i) for i in range(len(aux_chain))]
    step = build_step(aux_steps, out_step)
    init = build_init([a.init for a in aux_chain], out_init)
    return ("get", ("fold_s", step, init, ("var", listvar)), ("int", out_index))


# ============================================================================================
# LEVER B (X4.4) EXTENDED to a posited aux chain of ARBITRARY depth. Forward-run the KNOWN aux chain to
# get its per-prefix trajectory, read the OUTPUT component's trajectory from the oracle's prefix I/O,
# and derive the output step's own (state, elem) -> next table by lookup. A missing prefix breaks that
# one chain (honest degradation). This is the deduction that collapses the deep search to one shallow
# OE step-search over the top component.
# ============================================================================================
def aux_trajectory(prefix: tuple, aux_chain: list[Aux]) -> list[tuple]:
    """The (k-1)-tuple auxiliary state BEFORE each element (index i = state after i elements)."""
    steps = [aux_chain[i].step_at(i) for i in range(len(aux_chain))]
    acc = tuple(a.init for a in aux_chain)
    out = [acc]
    for e in prefix:
        acc = tuple(od.evaluate(s, {_A: acc, _E: e}) for s in steps)
        out.append(acc)
    return out


def derive_output_step_examples(outer: list, listvar: str, aux_chain: list[Aux], out_init: int) -> list:
    """Derive the output component's (full_state, elem) -> out_next table. `outer` is prefix-closed
    oracle I/O; the auxiliary trajectory is POSITED by forward-running the chain (no oracle for it —
    a wrong chain is caught by re-execution, propose-verify). Returns deduped [(step_env, want)]."""
    out_lut = {tuple(env[listvar]): want for env, want in outer}
    derived: list = []
    seen: set = set()
    for env, _ in outer:
        xs = tuple(env[listvar])
        traj = aux_trajectory(xs, aux_chain)
        out_acc = out_init
        for i in range(len(xs)):
            pref_next = xs[: i + 1]
            if pref_next not in out_lut:
                break
            out_next = out_lut[pref_next]
            state = traj[i] + (out_acc,)                    # full k-tuple BEFORE adding xs[i]
            key = (repr(state), repr(xs[i]))
            if key not in seen:
                seen.add(key)
                derived.append(({_A: state, _E: xs[i]}, out_next))
            out_acc = out_next
    return derived


# ============================================================================================
# SYNTHESIS ENTRY POINTS — each returns a rich result dict with an HONEST split of the work spent:
#   synth_evals   : oe_enumerate candidate evaluations (the search cost, 0 when an analogy is reused)
#   verify_execs  : whole-program re-executions during the verification anchor (the propose-verify cost)
# so the signal-4 harness can plot the TRUE per-wall work and show where the ledger removes the search.
# ============================================================================================
def synthesize_projection_chain(outer: list, listvar: str, verify: list, aux_chain: list[Aux], *,
                                 out_init: int = 0, analogy_template: Any = None,
                                 binary=("max2", "min2", "add", "sub"), max_nodes: int = 9,
                                 node_budget: int = 80000, time_budget: float = 6.0) -> dict:
    """Cross a wall with a projection-chain scheme of depth k = len(aux_chain)+1.

    If `analogy_template` is supplied (a promoted output-step template from a resonant past recipe),
    try it FIRST by direct RE-EXECUTION — no search: this is the compounding shortcut that makes a
    later wall cost ~0 synthesis evals. Otherwise DERIVE the output-step table and OE-SYNTHESISE it.
    Either way the VERIFICATION ANCHOR (`od.fitness(prog, verify) >= 1.0`) gates the result."""
    out_index = len(aux_chain)
    verify_execs = 0

    # --- compounding shortcut: reuse a promoted step template by analogy (index shift), verify only ---
    if analogy_template is not None:
        out_step = instantiate_rel(analogy_template, out_index)
        prog = assemble_projection(aux_chain, out_step, out_init, listvar)
        verify_execs += len(verify)
        if od.fitness(prog, verify) >= 1.0:
            return {"solved": True, "verified": True, "via": "analogy", "tree": prog,
                    "out_step": out_step, "out_step_template": analogy_template,
                    "program": od.to_source(prog), "synth_evals": 0, "verify_execs": verify_execs,
                    "k": out_index + 1, "out_index": out_index}

    # --- fresh discovery: derive the top-step table, OE-synthesise it ---
    derived = derive_output_step_examples(outer, listvar, aux_chain, out_init)
    if not derived:
        return {"solved": False, "via": "derive", "reason": "empty-derivation", "tree": None,
                "synth_evals": 0, "verify_execs": verify_execs, "k": out_index + 1}
    leaves = ss._proj_step_leaves(out_index + 1)
    r = ss.oe_enumerate(derived, leaves, unary=(), binary=binary, max_nodes=max_nodes,
                        node_budget=node_budget, time_budget=time_budget)
    synth_evals = r["evals"]
    if not r["solved"]:
        return {"solved": False, "via": "oe", "reason": "no-consistent-step", "tree": None,
                "synth_evals": synth_evals, "verify_execs": verify_execs, "k": out_index + 1}
    out_step = r["tree"]
    prog = assemble_projection(aux_chain, out_step, out_init, listvar)
    verify_execs += len(verify)
    if od.fitness(prog, verify) >= 1.0:
        return {"solved": True, "verified": True, "via": "oe", "tree": prog, "out_step": out_step,
                "out_step_template": relativize(out_step, out_index), "program": od.to_source(prog),
                "synth_evals": synth_evals, "verify_execs": verify_execs, "k": out_index + 1,
                "out_index": out_index}
    return {"solved": False, "via": "oe", "reason": "reexec-failed", "tree": None,
            "synth_evals": synth_evals, "verify_execs": verify_execs, "k": out_index + 1}


def _final_state(prefix: tuple, aux_chain: list[Aux]) -> tuple:
    steps = [aux_chain[i].step_at(i) for i in range(len(aux_chain))]
    acc = tuple(a.init for a in aux_chain)
    for e in prefix:
        acc = tuple(od.evaluate(s, {_A: acc, _E: e}) for s in steps)
    return acc


def synthesize_computed_projection(outer: list, listvar: str, verify: list, aux_chain: list[Aux], *,
                                   binary=("sub", "add", "max2", "min2", "idiv"), max_nodes: int = 7,
                                   node_budget: int = 60000, time_budget: float = 4.0) -> dict:
    """Cross a wall whose output is a COMPUTED PROJECTION pi over the FINAL k-tuple of generic
    auxiliaries (e.g. range = max - min: aux chain [running_max, running_min], pi = sub(get0, get1)).
    Runs the aux chain to its final state per example, then OE-synthesises pi mapping final-state ->
    output, and VERIFIES by re-execution. The second proposer move-type (LIFT + PROJECT, no per-prefix
    output deduction)."""
    k = len(aux_chain)
    proj_ex: list = []
    seen: set = set()
    for env, want in outer:
        st = _final_state(tuple(env[listvar]), aux_chain)
        key = repr(st)
        if key in seen:
            continue
        seen.add(key)
        proj_ex.append(({_A: st}, want))
    leaves = [_g(j) for j in range(k)] + [("int", 0), ("int", 1)]
    r = ss.oe_enumerate(proj_ex, leaves, unary=(), binary=binary, max_nodes=max_nodes,
                        node_budget=node_budget, time_budget=time_budget)
    synth_evals = r["evals"]
    if not r["solved"]:
        return {"solved": False, "via": "computed-proj", "reason": "no-projection", "tree": None,
                "synth_evals": synth_evals, "verify_execs": 0, "k": k}
    pi = r["tree"]
    aux_steps = [aux_chain[i].step_at(i) for i in range(k)]
    step = build_step(aux_steps[:-1], aux_steps[-1])
    init = build_init([a.init for a in aux_chain[:-1]], aux_chain[-1].init)
    fold = ("fold_s", step, init, ("var", listvar))
    # substitute the fold result into pi's _a to form a single evaluable program tree
    prog = _substitute_a(pi, fold)
    verify_execs = len(verify)
    if od.fitness(prog, verify) >= 1.0:
        return {"solved": True, "verified": True, "via": "computed-proj", "tree": prog,
                "projection": pi, "program": od.to_source(prog), "synth_evals": synth_evals,
                "verify_execs": verify_execs, "k": k}
    return {"solved": False, "via": "computed-proj", "reason": "reexec-failed", "tree": None,
            "synth_evals": synth_evals, "verify_execs": verify_execs, "k": k}


def _substitute_a(tree: Any, replacement: Any) -> Any:
    """Replace every ('var', _A) leaf in `tree` with `replacement` (used to inline the fold result into
    a computed projection pi so the whole thing is one evaluable program)."""
    if not isinstance(tree, tuple) or not tree:
        return tree
    if tree == ("var", _A):
        return replacement
    return tuple([tree[0]] + [_substitute_a(c, replacement) if isinstance(c, tuple) else c for c in tree[1:]])


# ============================================================================================
# GENERIC PROTOTYPE RECOGNISERS — the task-independent behaviour a scheme config is INTENDED to compute,
# derived structurally from the config (order statistic for a projection chain of depth k; a canonical
# aggregate for a computed projection). Used ONLY by the VSA ranker to ORDER candidate schemes; the
# actual program is always independently synthesised + verified (X4.5's "recognition vocabulary, not the
# answer" discipline). NOTE (v2 frontier): replacing these hand-derived prototypes with a small LEARNED
# recogniser trained on (failure-signature -> winning-scheme) pairs is the one place a N3-legal learned
# model would turn recombination into open-ended generation — see proposer.py.
# ============================================================================================
def kth_desc(xs: tuple, k: int) -> int:
    a = sorted(xs, reverse=True)
    return a[k] if len(a) > k else 0


def order_stat_prototype(depth: int) -> Callable[[dict], int]:
    """depth-k projection chain is intended to compute the k-th order statistic (k-th largest)."""
    return lambda e, _k=depth - 1: kth_desc(tuple(e.get("xs", ())), _k)


def computed_prototype(name: str) -> Callable[[dict], int]:
    xs = lambda e: tuple(e.get("xs", ()))
    return {
        "range": lambda e: (max(xs(e)) - min(xs(e)) if xs(e) else 0),
        "sum": lambda e: od._clamp_int(sum(xs(e))),
        "amplitude_hi": lambda e: (max(xs(e)) if xs(e) else 0),
    }[name]
