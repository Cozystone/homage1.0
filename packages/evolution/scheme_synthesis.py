# -*- coding: utf-8 -*-
"""X4.4 — SCHEME SYNTHESIS: the symbolic answer to the depth-5 wall (docs/ATANOR_X4_4_scheme_synthesis.md).

WHY THIS FILE EXISTS (the X4.4 question)
----------------------------------------
X4.3 measured a hard wall: the engine self-invented ONE new primitive KIND (segmentation, 450 evals) but
unguided evolutionary search EXPLODES at depth>=5. `seq_sort` (d7) reached fitness 0.50, `seq_second_max`
(d6) overfit train and failed holdout, `grid_num_objects` (d5) plateaued at 0.61 — all at ~6.4e4 evals.
Free-form `fix` + mutation cannot assemble deep recursion scaffolds.

The field's history already crossed this wall PURELY SYMBOLICALLY. lambda^2 (Feser et al., PLDI 2015)
synthesised fold/map data-structure transformations from I/O with ZERO neural prior, by pairing
INDUCTIVE GENERALISATION (hypothesise a combinator) with DEDUCTION (derive the missing sub-function's OWN
I/O examples) and bottom-up ENUMERATION with OBSERVATIONAL-EQUIVALENCE pruning. X4.3's free-form fix +
evolutionary mutation is exactly the trap lambda^2 avoided; the fix is the STRUCTURE OF THE SEARCH.

THE THREE SYMBOLIC LEVERS (philosophy-native: structure>memorisation, verification-anchored, neural 0)
------------------------------------------------------------------------------------------------------
  (A) NAMED RECURSION SCHEMES — `fold_s` / `para_s` / `unfold_s` (this module registers them as ADDITIVE,
      fuel-bounded interpreter ops via open_domain._EXT_OPS — never exec'd, same safety as the meta-basis).
      The schemes bind FRESH variables `_a` (accumulator) / `_e` (element) / `_rest` (suffix) so a base
      higher-order body nested in a step (map/filter, which bind _x/_i) does NOT shadow the scheme element
      — the same single-bound-variable ceiling `fix`/`_r` broke in X4.3, now solved for list-building folds.
      One deep search (sort = fold(insert,[])) becomes a PIPELINE of shallow step-function searches.

  (B) lambda^2 DEDUCTION — the wall-crossing core. When a fold is hypothesised, UNROLL it over each example
      list to DERIVE the step's own concrete I/O: for a LEFT fold whose accumulator is the running result,
      acc_i = f(prefix_i), so given PREFIX-CLOSED outer examples the intermediate accumulators are literally
      the outputs on shorter inputs, and step((acc_i, x_i)) -> acc_{i+1} falls out by table lookup. The deep
      search collapses to "derive examples + shallow search" — the structure by which a human learns `insert`
      from watching a sort. Every derived-example solution is VERIFIED by re-running the whole scheme on the
      original outer I/O (the verification anchor: a deduced step that doesn't reproduce the outer I/O is
      rejected).

  (C) OBSERVATIONAL-EQUIVALENCE ENUMERATION — replaces evolutionary mutation for the step search with
      bottom-up, SIZE-LAYERED enumeration that keeps ONE representative per observed BEHAVIOUR on the
      (derived) examples, priority-ordered by MDL/size (X1's compression principle). branching^depth
      collapses to "number of distinct behaviours" — the Transit/Duet standard our evolutionary search
      lacked. Type-directed operand gating bounds the binary-combination fan-out.

FUSION with the rest of the stack — a discovered step/scheme PROMOTES into a named primitive (X4.2's
`_promote_primitive`), so sort, once invented, opens `median`/`second_max` as shallow compositions (the
compounding channel); to_source rendering keeps promotion's source-dedup exact.

SAFETY. Pure interpretation over int|str|tuple. The schemes decrement the shared fuel budget per element
exactly like map/reduce and cap the built list at MAX_LEN, so total termination is preserved; no exec/eval
anywhere. Registration is ADDITIVE — open_domain._EXT_OPS is consulted only for keys the base grammar never
emits, so the live autonomous loop is byte-identical whether or not this module is imported.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any, Callable

from packages.evolution import open_domain as od

# ============================================================================================
# SCHEME-BOUND VARIABLES — fresh names, distinct from the base bodies' _x/_i/_acc and the fix _r, so a
# base map/filter nested inside a step body cannot shadow the scheme's element/accumulator. This is the
# structural key that makes `insert` (filter over the accumulator, compared to the fold ELEMENT) expressible.
# ============================================================================================
_A, _E, _REST = "_a", "_e", "_rest"
SCHEME_OPS = ("fold_s", "para_s", "unfold_s", "unit")


# ============================================================================================
# LEVER A — the recursion-scheme interpreter (additive, fuel-bounded; registered into open_domain._EXT_OPS)
# ============================================================================================
def _h_unit(t: Any, env: dict, fuel: list, ev: Callable) -> Any:
    """Singleton list constructor: unit(x) = (x,). The base grammar can build lists via range/map/filter
    but has no cons/singleton for an arbitrary element — a genuine gap for list-building recursion schemes
    (prepending the fold element into the accumulator). A fundamental constructor, like range."""
    return (ev(t[1], env, fuel),)


def _h_fold_s(t: Any, env: dict, fuel: list, ev: Callable) -> Any:
    """fold_s(step, init, xs): LEFT fold. acc_0 = init; acc_{i+1} = step(acc_i, x_i) with _a=acc, _e=x_i in
    scope. Fuel-bounded (one decrement per element, shared budget) so it terminates exactly like reduce."""
    _, step, init, src = t
    acc = ev(init, env, fuel)
    seq = od._as_seq(ev(src, env, fuel))[: od.MAX_LEN]
    for e in seq:
        if fuel[0] <= 0:
            break
        fuel[0] -= 1
        acc = ev(step, {**env, _A: acc, _E: e}, fuel)
    return acc


def _h_para_s(t: Any, env: dict, fuel: list, ev: Callable) -> Any:
    """para_s(step, init, xs): a LEFT paramorphism — like fold_s but the step ALSO sees the remaining
    suffix `_rest` (the elements after _e). This lets a step act with lookahead (e.g. stop-on-condition
    insert) that a plain fold cannot express. Same fuel discipline."""
    _, step, init, src = t
    acc = ev(init, env, fuel)
    seq = od._as_seq(ev(src, env, fuel))[: od.MAX_LEN]
    for i, e in enumerate(seq):
        if fuel[0] <= 0:
            break
        fuel[0] -= 1
        acc = ev(step, {**env, _A: acc, _E: e, _REST: seq[i + 1:]}, fuel)
    return acc


def _h_unfold_s(t: Any, env: dict, fuel: list, ev: Callable) -> Any:
    """unfold_s(step, seed, cnt): grow a list by iterating step on _a (the anamorphism dual of fold).
    Length is capped at min(cnt, MAX_LEN); fuel-bounded per element."""
    _, step, seed, cnt = t
    acc = ev(seed, env, fuel)
    n = max(0, min(od.MAX_LEN, od._as_int(ev(cnt, env, fuel))))
    out = [acc]
    for _ in range(n - 1):
        if fuel[0] <= 0:
            break
        fuel[0] -= 1
        acc = ev(step, {**env, _A: acc}, fuel)
        out.append(acc)
    return tuple(out)[: od.MAX_LEN]


_HANDLERS = {"unit": _h_unit, "fold_s": _h_fold_s, "para_s": _h_para_s, "unfold_s": _h_unfold_s}


def register(force: bool = False) -> None:
    """Install the scheme ops into open_domain's additive extension registry. Inert for every base/meta
    program (dispatched only on keys the base grammar never emits). ATANOR_SCHEME_SYNTH=0 opts out (the
    registry then stays empty, for an explicit byte-identical A/B); default is to register on import."""
    if not force and os.environ.get("ATANOR_SCHEME_SYNTH", "1") == "0":
        return
    od._EXT_OPS.update(_HANDLERS)


def unregister() -> None:
    for k in _HANDLERS:
        od._EXT_OPS.pop(k, None)


register()


# ============================================================================================
# LEVER C — OBSERVATIONAL-EQUIVALENCE bottom-up enumerator (MDL/size-layered). One representative per
# observed behaviour on the example inputs; type-directed operand gating; returns the minimal solver and
# the number of candidate evaluations spent (the honest "evals" metric, comparable to X4.3's pop*gens).
# ============================================================================================
_SEQ_T = (tuple, str)

# operand-type gates (prune nonsense combinations so binary fan-out stays bounded)
_UNARY_GATE: dict[str, Callable[[type], bool]] = {
    "len": lambda a: a in _SEQ_T, "closure": lambda a: a is tuple, "rev": lambda a: a in _SEQ_T,
    "unit": lambda a: a is int, "range": lambda a: a is int,
}
_BINARY_GATE: dict[str, Callable[[type, type], bool]] = {
    "cat": lambda a, b: a is tuple and b is tuple,
    "add": lambda a, b: a is int and b is int, "sub": lambda a, b: a is int and b is int,
    "mul": lambda a, b: a is int and b is int, "idiv": lambda a, b: a is int and b is int,
    "mod": lambda a, b: a is int and b is int, "min2": lambda a, b: a is int and b is int,
    "max2": lambda a, b: a is int and b is int,
    "get": lambda a, b: a in _SEQ_T and b is int,
    "edges": lambda a, b: a is tuple and b is int, "reach": lambda a, b: a is tuple and b is int,
}


def pred_menu(body_vars: tuple = ("_x", "_i"), consts: tuple = (0, 1, 2, 3)) -> list:
    """The bounded predicate set for `filter`: compare the iterated element _x against each other body
    variable and each small constant, over every comparison operator. Generic (not the answer): the search
    still has to discover WHICH predicate and HOW to compose the filter into the program."""
    rhs = [("var", v) for v in body_vars if v != "_x"] + [("int", c) for c in consts]
    return [("cmp", op, ("var", "_x"), r) for op in ("<", "<=", "==", "!=", ">", ">=") for r in rhs]


def oe_enumerate(examples: list, leaves: list, *, unary: tuple = (), binary: tuple = (),
                 use_filter: bool = False, filter_preds: tuple = (), prims: tuple = (),
                 max_nodes: int = 12, max_bank: int = 8000, node_budget: int = 400000,
                 time_budget: float = 60.0) -> dict:
    """Bottom-up, size-layered synthesis with observational-equivalence dedup.

    examples : [(env, want)]. Programs are evaluated on the example inputs; a candidate whose outputs equal
               `want` on EVERY example (exactly) wins. Two programs with the same output tuple are
               observationally equivalent -> only the smaller is kept (MDL / Occam == X1 compression).
    prims    : promoted primitive templates applied as a unary op (the compounding channel — e.g. `sort`).
    Returns {solved, program, tree, evals, bank, size}.
    """
    inputs = [env for env, _ in examples]
    wants = [want for _, want in examples]
    t0 = time.time()
    reps: dict[tuple, Any] = {}                 # behaviour-signature -> smallest tree (OE representative)
    by_size: dict[int, list] = defaultdict(list)  # construction-size -> [(tree, py_type)]
    n_evals = [0]

    def evaluate_all(tree: Any):
        n_evals[0] += 1
        try:
            return [od.evaluate(tree, env) for env in inputs]
        except Exception:
            return None

    def consider(tree: Any, size: int):
        # CONSTRUCTION size (each op node = +1; a promoted primitive counts as ONE symbol — the MDL reuse
        # credit that makes a promoted `sort` a cheap building block, decoupled from its internal expansion).
        vals = evaluate_all(tree)
        if vals is None:
            return None
        if all(v == w for v, w in zip(vals, wants)):
            return (tree, size)                  # EXACT solver
        sig = tuple(repr(v) for v in vals)
        if sig in reps or len(reps) >= max_bank:
            return None
        reps[sig] = tree
        by_size[size].append((tree, type(vals[0]) if vals else int))
        return None

    for lf in leaves:                            # size-1 layer
        w = consider(lf, 1)
        if w is not None:
            return _win(w[0], w[1], n_evals[0], reps)

    for size in range(2, max_nodes + 1):
        if time.time() - t0 > time_budget or n_evals[0] > node_budget:
            break
        # --- unary ops (+ promoted primitives), child size = size-1 ---
        for child, ct in list(by_size.get(size - 1, [])):
            for key in unary:
                if _UNARY_GATE[key](ct):
                    w = consider((key, child), size)
                    if w is not None:
                        return _win(w[0], w[1], n_evals[0], reps)
            for _label, tmpl, arity in prims:    # apply a promoted primitive to a tuple (arity-1 hole)
                if ct is tuple and arity == 1:
                    w = consider(od._instantiate(tmpl, [child]), size)
                    if w is not None:
                        return _win(w[0], w[1], n_evals[0], reps)
        # --- filter(pred, src): the predicate counts as a fixed size-3 sub-term, so src size = size-4 ---
        if use_filter and size >= 5:
            for src, st in list(by_size.get(size - 4, [])):
                if st is not tuple:
                    continue
                for pred in filter_preds:
                    w = consider(("filter", pred, src), size)
                    if w is not None:
                        return _win(w[0], w[1], n_evals[0], reps)
        # --- binary ops: op(a,b), size = 1 + sa + sb ---
        for sa in range(1, size - 1):
            sb = size - 1 - sa
            la, lb = by_size.get(sa), by_size.get(sb)
            if not la or not lb:
                continue
            for a, at in list(la):
                for b, bt in list(lb):
                    for key in binary:
                        if _BINARY_GATE[key](at, bt):
                            w = consider((key, a, b), size)
                            if w is not None:
                                return _win(w[0], w[1], n_evals[0], reps)
    return {"solved": False, "program": None, "tree": None, "evals": n_evals[0],
            "bank": len(reps), "size": None}


def _win(tree: Any, size: int, evals: int, reps: dict) -> dict:
    return {"solved": True, "program": od.to_source(tree), "tree": tree, "evals": evals,
            "bank": len(reps), "size": size}


# ============================================================================================
# LEVER B — lambda^2 DEDUCTION for fold_s. From PREFIX-CLOSED outer examples, derive the step's own I/O by
# unrolling the fold: for a left fold whose accumulator is the running result, the intermediate accumulator
# after i elements is exactly the output on the length-i prefix (a table lookup), so
# step((acc_i, x_i)) -> acc_{i+1} is deduced with no search. Verified by re-running the scheme.
# ============================================================================================
_MISSING = object()


def prefix_closed_io(ref: Callable[[dict], Any], listvar: str, *, n_lists: int, max_len: int,
                     rng, lo: int = 0, hi: int = 7, min_len: int = 0) -> list:
    """Sample outer examples that are PREFIX-CLOSED: for each sampled list, include every prefix (length
    0..len). This is a legitimate CHOICE OF INPUTS to query the reference oracle on (like showing a human
    sort([3]), sort([3,1]), sort([3,1,2])); the reference is still the only signal, `ref` is never exposed,
    and the step is DISCOVERED from the derived I/O. Returns [(env, out)] deduped by input."""
    seen: set = set()
    out: list = []
    for _ in range(n_lists):
        L = rng.randint(min_len, max_len)
        base = tuple(rng.randint(lo, hi) for _ in range(L))
        for i in range(len(base) + 1):
            pref = base[:i]
            if pref in seen:
                continue
            seen.add(pref)
            env = {listvar: pref}
            out.append((env, ref(env)))
    return out


def derive_fold_step_examples(outer: list, listvar: str, init: Any) -> list:
    """Unroll a hypothesised LEFT fold over each outer example and derive the step's (acc, elem)->acc'
    examples by looking up the output on each prefix. `init` is the acc before the first element (the
    output on the empty list). Missing intermediates break that one chain (honest degradation), never the
    whole derivation. Returns deduped [(step_env, want_acc_next)]."""
    lut = {tuple(env[listvar]): want for env, want in outer}
    derived: list = []
    seen: set = set()
    for env, want in outer:
        xs = tuple(env[listvar])
        acc: Any = init
        for i in range(len(xs)):
            nxt = xs[: i + 1]
            acc_next = lut.get(nxt, want if i == len(xs) - 1 else _MISSING)
            if acc_next is _MISSING:
                break
            key = (repr(acc), repr(xs[i]), repr(acc_next))
            if key not in seen:
                seen.add(key)
                derived.append(({_A: acc, _E: xs[i]}, acc_next))
            acc = acc_next
    return derived


def _empty_tuple_tree() -> Any:
    return ("range", ("int", 0))                 # evaluates to (), the natural [] init for list folds


def synthesize_fold(outer: list, listvar: str, verify: list, *, step_unary=("unit",),
                    step_binary=("cat", "min2", "max2"), step_filter=True,
                    step_pred_vars=("_x", "_e"), step_pred_consts=(0, 1), init_trees=None,
                    max_nodes: int = 18, node_budget: int = 400000, time_budget: float = 90.0) -> dict:
    """Hypothesise `f = fold_s(step, init, xs)`, DEDUCE the step's I/O (Lever B), SYNTHESISE the step by OE
    enumeration (Lever C), and VERIFY the whole scheme on held-out full-length examples (the anchor).
    `verify` are full-length (env, out) pairs the fold is re-run on; a step that solves the derived
    examples but fails re-execution is rejected. Returns the scheme program + total evals."""
    lut = {tuple(env[listvar]): want for env, want in outer}
    if init_trees is None:
        empty_out = lut.get((), ())
        init_trees = [(_empty_tuple_tree(), ())]        # [] for list-building folds (sorted(())==())
        if empty_out != ():
            init_trees = [(("int", 0), 0)] + init_trees
    leaves = [("var", _A), ("var", _E), ("int", 0), ("int", 1)]
    preds = tuple(pred_menu(body_vars=step_pred_vars, consts=step_pred_consts))
    total_evals = 0
    for init_tree, init_val in init_trees:
        derived = derive_fold_step_examples(outer, listvar, init_val)
        if not derived:
            continue
        res = oe_enumerate(derived, leaves, unary=step_unary, binary=step_binary,
                           use_filter=step_filter, filter_preds=preds, max_nodes=max_nodes,
                           node_budget=node_budget, time_budget=time_budget)
        total_evals += res["evals"]
        if not res["solved"]:
            continue
        prog = ("fold_s", res["tree"], init_tree, ("var", listvar))
        if od.fitness(prog, verify) >= 1.0:                # VERIFICATION ANCHOR: re-run the whole scheme
            return {"solved": True, "scheme": "fold_s", "program": od.to_source(prog), "tree": prog,
                    "step_program": res["program"], "step_tree": res["tree"],
                    "derived_examples": len(derived), "step_evals": res["evals"],
                    "evals": total_evals, "verified": True}
    return {"solved": False, "scheme": "fold_s", "program": None, "tree": None, "evals": total_evals}


# ============================================================================================
# TOP-LEVEL — try the cheap DIRECT composition first (OE), then the fold scheme with deduction.
# ============================================================================================
def synthesize_direct(examples: list, leaves: list, *, unary=(), binary=(), use_filter=False,
                      pred_vars=("_x", "_i"), prims=(), max_nodes: int = 12,
                      node_budget: int = 400000, time_budget: float = 60.0) -> dict:
    """Direct bottom-up OE composition (no recursion scheme) — the lever that cracks a deep COMPOSITION the
    evolutionary search could not assemble (e.g. num_objects = len(filter(_x==_i, closure(edges(xs,n))))),
    and the channel through which a promoted primitive opens a shallow dependent."""
    preds = tuple(pred_menu(body_vars=pred_vars))
    return oe_enumerate(examples, leaves, unary=unary, binary=binary, use_filter=use_filter,
                        filter_preds=preds, prims=prims, max_nodes=max_nodes,
                        node_budget=node_budget, time_budget=time_budget)


def promote_scheme(state: dict, family: str, tree: Any) -> bool:
    """Promote a discovered scheme/step program into the solver's named-primitive vocabulary (X4.2 path):
    variabilise the family's primary input into a shared hole, gate for non-degeneracy. Once promoted, a
    dependent (median/second_max) instantiates the KIND in one step — the causal-compounding channel."""
    state.setdefault("promoted", {f: [] for f in od._FAMILIES})
    return od._promote_primitive(state, family, tree)


def promoted_primitives(state: dict, family: str) -> tuple:
    """Promoted templates as (label, template, arity) triples for oe_enumerate's `prims` channel."""
    out = []
    for i, p in enumerate(state.get("promoted", {}).get(family, ())):
        out.append((f"prim{i}", p["template"], p["arity"]))
    return tuple(out)


# ================================================================================================
# X4.5 FUSION — RANKER-DRIVEN SCHEME SELECTION (docs/ATANOR_roadmap_v2_consolidated.md A1)
# ------------------------------------------------------------------------------------------------
# WHY THIS SECTION EXISTS (the A1 question — the wall X4.4 NAMED)
# --------------------------------------------------------------
# X4.4 crossed the depth wall for sort (fold + identity-projection deduction) but flagged the next real
# wall: SCHEME SELECTION. `seq_second_max` does NOT self-invent standalone because its output is a scalar
# PROJECTION of a pair-accumulator state (max1, max2): a LEFT fold's intermediate accumulators are the
# prefix OUTPUTS only when the projection is the IDENTITY, so the second_max output is not the accumulator
# and blind fold-deduction (`derive_fold_step_examples`) hits a FUNCTIONAL CONFLICT (measured: 2 conflicts
# on the derived scalar-state examples) — the honest signal that the state is INSUFFICIENT. X4.4 only
# crossed second_max by COMPOUNDING (reusing a promoted sort), never standalone.
#
# THE TWO LEVERS THIS SECTION ADDS (both No-LLM, pure FHRR algebra + symbolic search, verification-anchored)
# ----------------------------------------------------------------------------------------------------------
#   (D) THE PAIR-ACCUMULATOR PROJECTION FAMILY — a fold whose accumulator is a k-tuple and whose OUTPUT is a
#       PROJECTION of it (a component index). One component is the observed OUTPUT (its prefix trajectory is
#       the oracle's prefix I/O); the other is a GENERIC auxiliary running fold (running max/min/sum/…, each
#       a grammar fold over one meta-basis op) whose trajectory is computed by EVALUATING that grammar
#       program (no injected knowledge). Pairing the auxiliary with the output RE-CLOSES the deduction: the
#       full-state trajectory (aux_i, out_i) is known, so each component's own (state,elem)->comp' examples
#       fall out by table lookup exactly as in Lever B — and the deep search again collapses to two shallow
#       OE step-searches. The auxiliary is DISCOVERED, not baked: a wrong auxiliary either CONFLICTS on the
#       full state or FAILS the re-execution anchor (measured: running_sum is conflict-free but re-executes
#       at 0.81 < 1.0 -> rejected). second_max's true form (fold with a (max,second) accumulator, output =
#       2nd component) is now IN the hypothesis space, and it self-invents STANDALONE.
#
#   (E) X4.5 ALGEBRAIC RANKER -> SCHEME SELECTION — turn blind scheme enumeration into RANKED selection. A
#       fixed, task-independent library of generic seq/num BEHAVIOUR PROTOTYPES (sum/product/max/min/sorted/
#       second_max/…/num_objects), each mapped to a synthesis RECIPE (identity-fold / pair-accum-projection /
#       direct-composition), is ranked against the task's I/O by FHRR phasor resonance (packages/vsa_reasoning
#       behavior_signature.rank_candidates — a holographic hash of the I/O table, NO training). The top
#       prototype's recipe is tried first, so the doomed identity-fold search (~9e5 evals for second_max) is
#       SKIPPED. The ranker only ORDERS the search; the exact re-execution anchor still gates every solution
#       (propose-verify; 0 fabrication). The prototype library is the RECOGNITION vocabulary, never the
#       returned program — the grammar fold is still independently synthesised and verified.
#
# COMPOSABILITY / SAFETY. Behind ATANOR_SCHEME_SELECT (default on for the explicit synthesis entry points;
# the live autonomous loop never calls these, so it is byte-identical regardless). rank_candidates is
# imported LAZILY inside the selector so module import stays lightweight and byte-identical to X4.4. No
# exec/eval; pure interpretation + FHRR algebra. ATANOR_SCHEME_SELECT=0 falls back to blind (unranked)
# enumeration order, giving a clean A/B for the eval-efficiency gate.
# ================================================================================================

def _scheme_select_on() -> bool:
    """ATANOR_SCHEME_SELECT gates the RANKER (ordering). Off -> blind (fixed-order) enumeration, so the
    eval-efficiency gate has a clean A/B. Default on (the explicit entry points are not on the live path)."""
    return os.environ.get("ATANOR_SCHEME_SELECT", "1") != "0"


def aux_fold_menu() -> dict:
    """The GENERIC auxiliary scalar-fold menu — each entry is fold_s(<binop>(_a,_e), init, xs) over a single
    meta-basis primitive: a running max / min / sum / product / count. Task-independent (the SAME menu for
    every task); the pair-accumulator synthesiser DISCOVERS which auxiliary Markov-closes the output by the
    conflict-free + re-execution gates, so no auxiliary is baked to a task. min uses the +inf sentinel
    (_INT_CLAMP) as its fold identity."""
    return {
        "running_max": (("max2", ("var", _A), ("var", _E)), 0),
        "running_min": (("min2", ("var", _A), ("var", _E)), od._INT_CLAMP),
        "running_sum": (("add", ("var", _A), ("var", _E)), 0),
        "running_prod": (("mul", ("var", _A), ("var", _E)), 1),
        "running_cnt": (("add", ("var", _A), ("int", 1)), 0),
    }


def _proj_step_leaves(k: int) -> list:
    """Leaves for synthesising a k-tuple accumulator's per-component step: every component projection
    get(_a, j) (so a component's update can read ANY component — the structural key that lets the 2nd-max
    update reference the running max) plus the fold element _e and the small constants 0/1."""
    comps = [("get", ("var", _A), ("int", j)) for j in range(k)]
    return comps + [("var", _E), ("int", 0), ("int", 1)]


def _derive_projected_step_examples(outer: list, listvar: str, init_tuple: tuple,
                                    acc_at: Callable[[tuple], Any]) -> tuple:
    """Lever B extended to a PROJECTED state. Unroll the fold over each outer example, reading the FULL
    k-tuple state trajectory `acc_at(prefix)` (auxiliary components computed by evaluating their grammar
    fold; the output component read from the oracle's prefix I/O). Derive EACH component j's own
    (state, elem) -> component_j' examples by table lookup. A FUNCTIONAL CONFLICT on the full state (same
    (state,elem) mapping to two different next states) means the hypothesised state is INSUFFICIENT for THIS
    auxiliary (the honest reject signal). Returns ([comp0_examples, ...], conflict: bool); on a missing
    prefix the chain breaks (honest degradation), never the whole derivation."""
    k = len(init_tuple)
    ex: list = [[] for _ in range(k)]
    seen: list = [set() for _ in range(k)]
    fmap: dict = {}
    for env, _ in outer:
        xs = tuple(env[listvar])
        acc: Any = init_tuple
        for i in range(len(xs)):
            nxt = xs[: i + 1]
            an = acc_at(nxt)
            if an is None:
                break
            key = (repr(acc), repr(xs[i]))
            if key in fmap and fmap[key] != an:
                return None, True                    # state-insufficiency conflict -> reject this auxiliary
            fmap[key] = an
            step_env = {_A: acc, _E: xs[i]}
            for j in range(k):
                kk = (key, repr(an[j]))
                if kk not in seen[j]:
                    seen[j].add(kk)
                    ex[j].append((step_env, an[j]))
            acc = an
    return ex, False


def synthesize_projection_fold(outer: list, listvar: str, verify: list, *, out_index: int = 1,
                               aux_menu: dict | None = None,
                               step_binary=("max2", "min2", "add", "sub"),
                               ranked_aux: tuple = (), max_nodes: int = 10,
                               node_budget: int = 200000, time_budget: float = 30.0) -> dict:
    """Lever D — hypothesise  output = get(fold_s(step, init, xs), out_index)  with a 2-tuple accumulator
    (one AUXILIARY running fold + the OUTPUT component). For each candidate auxiliary (menu order, or
    `ranked_aux` order when the ranker supplies one), form the pair-state (aux_i, out_i) over prefixes,
    DERIVE each component's own step I/O (`_derive_projected_step_examples`), OE-SYNTHESISE both component
    updates (`oe_enumerate`), assemble the fold, PROJECT component out_index, and VERIFY by re-execution on
    `verify` (the anchor). A wrong auxiliary CONFLICTS or fails verification -> rejected (no fabrication).
    This crosses `seq_second_max` STANDALONE (no promoted sort). Returns the scheme program + total evals."""
    if aux_menu is None:
        aux_menu = aux_fold_menu()
    out_lut = {tuple(env[listvar]): want for env, want in outer}
    out_empty = out_lut.get((), 0)
    leaves = _proj_step_leaves(2)
    aux_index = 1 - out_index
    order = [a for a in ranked_aux if a in aux_menu] or list(aux_menu)
    total = 0
    for aux_name in order:
        aux_step, aux_init = aux_menu[aux_name]

        def acc_at(prefix: tuple, _step=aux_step, _init=aux_init) -> Any:
            if prefix not in out_lut:
                return None
            a = od.evaluate(("fold_s", _step, ("int", _init), ("var", listvar)), {listvar: prefix})
            pair = [None, None]
            pair[aux_index] = a
            pair[out_index] = out_lut[prefix]
            return tuple(pair)

        init_pair = [None, None]
        init_pair[aux_index] = aux_init
        init_pair[out_index] = out_empty
        init_pair = tuple(init_pair)
        derived, conflict = _derive_projected_step_examples(outer, listvar, init_pair, acc_at)
        if conflict or derived is None or any(not e for e in derived):
            continue
        trees: list = []
        ok = True
        for comp_ex in derived:
            r = oe_enumerate(comp_ex, leaves, unary=(), binary=step_binary,
                             max_nodes=max_nodes, node_budget=node_budget, time_budget=time_budget)
            total += r["evals"]
            if not r["solved"]:
                ok = False
                break
            trees.append(r["tree"])
        if not ok:
            continue
        step = ("cat", ("unit", trees[0]), ("unit", trees[1]))
        init_tree = ("cat", ("unit", ("int", init_pair[0])), ("unit", ("int", init_pair[1])))
        prog = ("get", ("fold_s", step, init_tree, ("var", listvar)), ("int", out_index))
        if od.fitness(prog, verify) >= 1.0:                 # VERIFICATION ANCHOR (re-run the whole scheme)
            return {"solved": True, "scheme": "fold_s+proj", "program": od.to_source(prog), "tree": prog,
                    "auxiliary": aux_name, "out_index": out_index, "step_program": od.to_source(step),
                    "evals": total, "verified": True}
    return {"solved": False, "scheme": "fold_s+proj", "program": None, "tree": None, "evals": total}


# --- the generic scheme-prototype LIBRARY (recognition vocabulary) + FHRR ranker wiring ----------
def _xs(env: dict) -> tuple:
    return tuple(env.get("xs", ()))


def _kth_desc(env: dict, k: int) -> int:
    a = sorted(_xs(env), reverse=True)
    return a[k] if len(a) > k else 0


def _proto_product(env: dict) -> int:
    p = 1
    for x in _xs(env):
        p = od._clamp_int(p * x)
    return p


def _proto_num_objects(env: dict) -> int:
    lab = od._component_labels(od._grid_adjacency(env.get("xs", ()), env.get("n", 0)))
    return sum(1 for i, m in enumerate(lab) if m == i)


def scheme_library() -> dict:
    """The FIXED, task-independent library the ranker discriminates over: {name -> (behaviour_fn, recipe)}.
    Each behaviour_fn is a GENERIC seq/num transformation (a recognition prototype — an order statistic, a
    running aggregate, a segmentation count) computed from the task's input env; the recipe names the
    synthesis FAMILY the top match routes to. The prototypes are the SPACE OF SCHEMES the synthesiser can
    build, NOT an answer key: a match only ORDERS the search; the grammar program is independently
    synthesised and verified. `aux`/`out_index` on a pair-accum recipe are hints (the synthesiser still
    discovers/verifies the auxiliary)."""
    ident = {"family": "identity-fold"}
    direct = {"family": "direct"}
    return {
        # identity-projection folds (accumulator == output): the X4.4 path
        "sum":            (lambda e: od._clamp_int(sum(_xs(e))), ident),
        "product":        (_proto_product, ident),
        "max":            (lambda e: (max(_xs(e)) if _xs(e) else 0), ident),
        "min":            (lambda e: (min(_xs(e)) if _xs(e) else 0), ident),
        "sorted_asc":     (lambda e: tuple(sorted(_xs(e))), ident),
        # pair-accumulator PROJECTION folds (accumulator richer than output): the A1 path
        "second_max":     (lambda e: _kth_desc(e, 1),
                           {"family": "pair-accum", "out_index": 1, "aux": "running_max"}),
        "third_max":      (lambda e: _kth_desc(e, 2),
                           {"family": "pair-accum", "out_index": 2, "aux": "running_max"}),
        # direct compositions (no recursion scheme)
        "reverse":        (lambda e: _xs(e)[::-1], direct),
        "identity_seq":   (lambda e: _xs(e), direct),
        "num_objects":    (_proto_num_objects, {"family": "direct", "grid": True}),
        # residual recognitions (routed, but their synthesis is the honest boundary — see the A1 report)
        "max_minus_min":  (lambda e: (max(_xs(e)) - min(_xs(e)) if _xs(e) else 0),
                           {"family": "pair-accum-computed", "residual": True}),
        "count_distinct": (lambda e: len(set(_xs(e))),
                           {"family": "list-accum-len", "residual": True}),
    }


def rank_schemes(spec: list, library: dict | None = None) -> list:
    """Rank the scheme-prototype library against the task I/O `spec` = [(env, output)] by FHRR phasor
    resonance (packages/vsa_reasoning behavior_signature.rank_candidates — No-LLM, no training). Returns
    [(name, score, recipe)] sorted by score DESC. Imported LAZILY so this module's import stays byte-identical
    to X4.4 when selection is unused."""
    from packages.vsa_reasoning.behavior_signature import rank_candidates
    lib = library or scheme_library()
    cands = {name: fn for name, (fn, _recipe) in lib.items()}
    ranked = rank_candidates(spec, cands)
    return [(name, score, lib[name][1]) for name, score in ranked]


def select_and_synthesize(spec: list, outer: list, listvar: str, verify: list, *,
                          library: dict | None = None, max_fallback: int = 3,
                          identity_kw: dict | None = None, direct_kw: dict | None = None,
                          proj_kw: dict | None = None) -> dict:
    """A1 top-level — RANKER-DRIVEN scheme selection fused into the scheme/projection choice. Rank the
    generic prototype library against the task I/O (`spec`), then dispatch to the top recipe's synthesiser,
    falling through ranked order (up to `max_fallback`) on failure. `outer` is the prefix-closed I/O for
    deduction; `verify` the full-length anchor. Behind ATANOR_SCHEME_SELECT (off -> library ORDER, i.e.
    blind, so the eval gate has a clean A/B). The ranker only orders the search; every returned solution
    passes the exact re-execution anchor (propose-verify; no fabrication). Returns the synthesis result
    annotated with {selected, rank, rank_score, ranked, evals}."""
    lib = library or scheme_library()
    if _scheme_select_on():
        ranked = rank_schemes(spec, lib)
    else:                                                    # A/B: no ranker -> fixed library order
        ranked = [(name, 0.0, recipe) for name, (_fn, recipe) in lib.items()]
    total = 0
    attempts: list = []
    tried_families: set = set()                              # de-dup: never rerun the identical family search
    for name, score, recipe in ranked:
        if len(tried_families) >= max(1, max_fallback):
            break
        fam = recipe.get("family")
        if fam in tried_families:                            # e.g. sum/product/max all route to identity-fold
            continue
        tried_families.add(fam)
        rank_i = len(tried_families) - 1
        if fam == "identity-fold":
            kw = dict(step_binary=("cat", "add", "mul", "min2", "max2"), step_filter=True,
                      step_pred_vars=("_x", "_e"), step_pred_consts=(0, 1), max_nodes=18, time_budget=45.0)
            kw.update(identity_kw or {})
            res = synthesize_fold(outer, listvar, verify, **kw)
        elif fam == "pair-accum":
            kw = dict(out_index=recipe.get("out_index", 1),
                      ranked_aux=(recipe.get("aux"),) if recipe.get("aux") else ())
            kw.update(proj_kw or {})
            res = synthesize_projection_fold(outer, listvar, verify, **kw)
        elif fam == "direct":
            kw = dict(leaves=[("var", listvar), ("var", "n"), ("int", 0), ("int", 1)],
                      unary=("len", "closure", "rev"), binary=("edges", "reach", "get", "idiv"),
                      use_filter=True, pred_vars=("_x", "_i"), max_nodes=10, time_budget=30.0)
            kw.update(direct_kw or {})
            leaves = kw.pop("leaves")
            res = synthesize_direct(spec, leaves, **kw)
        else:                                                # residual families (pair-accum-computed / list-accum-len)
            res = {"solved": False, "scheme": fam, "program": None, "tree": None, "evals": 0,
                   "residual": True}
        total += res.get("evals", 0)
        attempts.append({"scheme": name, "family": fam, "solved": res.get("solved", False),
                         "evals": res.get("evals", 0)})
        if res.get("solved"):
            res.update({"selected": name, "rank": rank_i, "rank_score": score,
                        "evals": total, "attempts": attempts,
                        "ranked": [(n, round(s, 3)) for n, s, _ in ranked[:4]]})
            return res
    return {"solved": False, "selected": None, "evals": total, "attempts": attempts,
            "ranked": [(n, round(s, 3)) for n, s, _ in ranked[:4]]}
