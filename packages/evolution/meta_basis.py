# -*- coding: utf-8 -*-
"""X4.3 — META-BASIS: the generative substrate the engine invents NEW PRIMITIVE KINDS over.

WHY THIS FILE EXISTS (the X4.3 question)
----------------------------------------
X4.1/X4.2 measured a hard boundary: the loop can COMPOSE existing primitives (0->3-4 autonomous solves,
a2 reached linear) but cannot INVENT a new operation KIND. Tier-3 tasks (sort / dedup / second-max /
connected-components) are unreachable even with ideal stepping stones — the base grammar has no primitive
KIND for ordering-driven selection, unbounded conditional recursion, or transitive closure, AND its single
shared bound-variable scheme (_x/_i/_acc across every nested higher-order form) makes nested element
comparison inexpressible (you cannot compare an inner-loop element to an outer-loop element — same name).

THE DESIGN (honest key insight)
-------------------------------
Most "new primitive types" are expressible over a small, bounded-Turing-complete META-BASIS that is MORE
FUNDAMENTAL than the domain primitives. We add that substrate (in open_domain._ev, purely additive) and
let the ordinary invention machinery DISCOVER + NAME domain primitives over it:

  * bounded recursion / fixpoint  -> `fix`/`rec` with a FRESH parameter `_r` (fuel- and depth-capped,
    never exec'd). The fresh name is the crux: a recursive call carries the OUTER element inward, so
    nested comparison becomes expressible.  sort / second-max  ~=  recursion + comparison.
  * ordering                      -> `min2`/`max2` (shorten selection programs so the search can reach them).
  * relational / graph            -> `edges` (pairwise same-colour 4-adjacency), `reach` (transitive
    closure from a source), `closure` (connected-component labelling).  segmentation ~= adjacency + closure.

This module is the meta-aware GRAMMAR (random_tree_meta / mutate_meta / evolve_meta) — kept OUT of
open_domain so the live autonomous loop's search distribution is byte-identical (the interpreter merely
gained dead branches) — plus the DISCOVERY search (reusing compression_progress X1 as the learning-progress
signal), the grid tasks, and the PROMOTION of a discovered program into a NAMED primitive (reusing X4.2's
od._promote_primitive path). Nothing here is a domain primitive handed in: `reach`/`closure`/`fix` are
fundamental operators; SORT / OBJECT-SIZE / NUM-OBJECTS are what the engine must rediscover and name.

SAFETY. Pure interpretation over int|str|tuple; recursion is doubly bounded (global FUEL + MAX_REC depth);
no exec/eval anywhere; reference outputs are manufactured by the SAME bounded routines the interpreter uses
so a correct program matches the I/O EXACTLY (the external-verification discipline of X4.1).
"""
from __future__ import annotations

import random
from typing import Any, Callable

from packages.evolution import open_domain as od

# The meta-op menus. They are ENABLED PER EXPERIMENT (scoping): a discovery run turns on only the
# fundamental substrate the target KIND needs, which keeps the (much larger) recursive-program search
# tractable. Scoping the substrate is not handing in the answer — `reach`/`fix` are fundamental ops, the
# domain primitive (object-size / sort) is still rediscovered from I/O.
GRAPH_OPS = ("edges", "reach", "closure")
REC_OPS = ("fix", "min2", "max2")
ALL_META = GRAPH_OPS + REC_OPS


# ===========================================================================
# META-AWARE GRAMMAR — like od.random_tree but (a) meta ops can NEST (reach can wrap edges — the whole
# point, since a discovered domain primitive is a multi-op composition), and (b) inside a `fix` body the
# recursion parameter _r is a visible leaf and a `rec` self-call is allowed.
# ===========================================================================
def random_tree_meta(env_vars: list[str], rng: random.Random, depth: int, *, ops: tuple,
                     in_fix: bool = False, library: tuple = (), primitives: tuple = ()) -> Any:
    graph_on = any(o in ops for o in GRAPH_OPS)
    rec_on = any(o in ops for o in REC_OPS)
    grid_var = env_vars[0] if env_vars else None
    width_var = env_vars[1] if len(env_vars) >= 2 else None

    def sub(dv: list | None = None) -> Any:
        return random_tree_meta(dv if dv is not None else env_vars, rng, depth - 1, ops=ops,
                                in_fix=in_fix, library=library, primitives=primitives)

    if depth <= 0 or rng.random() < 0.28:
        if in_fix and rng.random() < 0.30:
            return ("var", od._R)                             # the recursion parameter is a real leaf
        if primitives and rng.random() < 0.18:
            return od._grow_primitive(rng.choice(primitives), env_vars, rng, depth,
                                      library=library, primitives=primitives)
        if library and rng.random() < 0.30:
            return rng.choice(library)
        return od._leaf(env_vars, rng)

    bvars = env_vars + [od._X, od._I, od._ACC]

    def subb() -> Any:                                        # a body position: _x/_i/_acc are in scope
        return random_tree_meta(bvars, rng, depth - 1, ops=ops, in_fix=in_fix,
                                library=library, primitives=primitives)

    def mk_grid() -> Any:
        return ("var", grid_var) if (grid_var and rng.random() < 0.75) else sub()

    def mk_width() -> Any:
        if width_var and rng.random() < 0.65:
            return ("var", width_var)
        return ("int", rng.randint(1, 4))

    def mk_edges() -> Any:
        return ("edges", mk_grid(), mk_width())

    def mk_adj() -> Any:                                      # an adjacency-typed argument
        return mk_edges() if rng.random() < 0.78 else sub()

    r = rng.random()
    # --- meta bands first (so the substrate actually appears) ---
    if graph_on and r < 0.24:
        choices = []
        if "edges" in ops:
            choices.append(("edges", mk_grid(), mk_width()))
        if "reach" in ops:
            src = ("int", rng.randint(0, 3)) if rng.random() < 0.7 else sub()
            choices.append(("reach", mk_adj(), src))
        if "closure" in ops:
            choices.append(("closure", mk_adj()))
        return rng.choice(choices)
    if rec_on and r < 0.42:
        choices = []
        if "min2" in ops:
            choices.append(("min2", sub(), sub()))
        if "max2" in ops:
            choices.append(("max2", sub(), sub()))
        if "fix" in ops:
            body = random_tree_meta(env_vars, rng, depth - 1, ops=ops, in_fix=True,
                                    library=library, primitives=primitives)
            choices.append(("fix", body, sub()))
        if in_fix and "fix" in ops and rng.random() < 0.5:
            choices.append(("rec", sub()))
        return rng.choice(choices)
    # --- base grammar (mirrors od.random_tree productions) ---
    if r < 0.55:
        return (rng.choice(od._NUM_OPS), sub(), sub())
    if r < 0.64:
        return rng.choice([("cat", sub(), sub()), ("rep", sub(), sub()), ("rev", sub()),
                           ("range", sub())])
    if r < 0.75:
        return rng.choice([("len", sub()), ("get", sub(), sub()),
                           ("slice", sub(), sub(), sub())])
    if r < 0.90:
        return rng.choice([
            ("map", subb(), sub()),
            ("filter", ("cmp", rng.choice(list(od._CMP)), subb(), subb()), sub()),
            ("reduce", subb(), sub(), sub()),
        ])
    return ("if", ("cmp", rng.choice(list(od._CMP)), sub(), sub()), sub(), sub())


def mutate_meta(tree: Any, env_vars: list[str], rng: random.Random, *, ops: tuple,
                in_fix: bool = False, library: tuple = (), primitives: tuple = ()) -> Any:
    """One local edit over the meta grammar: recurse into a random child (structure-preserving) or regrow
    a subtree with random_tree_meta (introduces/removes meta ops). Bounded like od.mutate."""
    kw = dict(ops=ops, library=library, primitives=primitives)
    if not isinstance(tree, tuple) or not tree:
        return random_tree_meta(env_vars, rng, 2, in_fix=in_fix, **kw)
    k = tree[0]
    if od._too_big(tree):
        return random_tree_meta(env_vars, rng, 3, in_fix=in_fix, **kw)
    r = rng.random()
    if r < 0.30:                                              # regrow whole (escape local optima)
        return random_tree_meta(env_vars, rng, min(4, 2 + rng.randint(0, 2)), in_fix=in_fix, **kw)
    if k in ("int",):
        return ("int", max(0, tree[1] + rng.choice([-2, -1, 1, 2])))
    if k == "str":
        return ("str", rng.choice(od._STR_CONSTS))
    if k == "var":
        return random_tree_meta(env_vars, rng, 1, in_fix=in_fix, **kw)
    if k == "cmp":
        if rng.random() < 0.5:
            return ("cmp", rng.choice(list(od._CMP)), tree[2], tree[3])
    child_fix = in_fix or (k == "fix")
    idx = [i for i in range(1, len(tree)) if isinstance(tree[i], tuple)]
    if idx:
        i = rng.choice(idx)
        # entering a fix body (child index 1 of a fix) makes _r visible + rec legal
        cf = child_fix if not (k == "fix" and i == 1) else True
        cvars = env_vars + [od._X, od._I, od._ACC]
        child = (mutate_meta(tree[i], cvars, rng, in_fix=cf, **kw) if rng.random() < 0.7
                 else random_tree_meta(cvars, rng, 2, in_fix=cf, **kw))
        return tuple(list(tree[:i]) + [child] + list(tree[i + 1:]))
    return random_tree_meta(env_vars, rng, 2, in_fix=in_fix, **kw)


def _bounded_meta(tree: Any, env_vars: list[str], rng: random.Random, ops: tuple) -> Any:
    if od._too_big(tree):
        return random_tree_meta(env_vars, rng, 3, ops=ops)
    return tree


def evolve_meta(tests: list, vars_: list[str], *, ops: tuple, pop: int = 160, generations: int = 300,
                rng_seed: int = 7, library: tuple = (), primitives: tuple = (),
                depth: int = 4) -> dict:
    """Gradient-free program search over the base grammar UNION the enabled meta-basis ops. Same shape as
    od.evolve (elitism + mutated offspring, ranked by the smoothed verifier, stop on an exact solver), but
    the generators are the meta-aware ones so the search can DISCOVER a multi-op domain primitive."""
    rng = random.Random(rng_seed)
    kw = dict(ops=ops, library=library, primitives=primitives)
    population = [_bounded_meta(random_tree_meta(vars_, rng, depth, **kw), vars_, rng, ops)
                 for _ in range(pop)]
    best, best_exact, solved_gen, gen = None, -1.0, None, 0
    # A TINY parsimony term breaks ties toward smaller programs (Occam / MDL — the same compression ethos
    # X1 ranks by). It never lets a near-miss outrank an exact solver (the penalty is < one example's
    # worth), but among equally-correct candidates it selects the clean minimal form, so a self-invented
    # primitive is discovered in its parsimonious spelling rather than a bloated equivalent.
    def _rank(t):
        return od.graded_fitness(t, tests) - 1e-4 * od._size(t)
    for gen in range(1, generations + 1):
        scored = sorted(((_rank(t), t) for t in population), key=lambda x: -x[0])
        for _g, t in scored[: max(4, pop // 8)]:
            e = od.fitness(t, tests)
            if e > best_exact or (e >= 1.0 and e == best_exact and best is not None
                                  and od._size(t) < od._size(best)):
                best_exact, best = e, t
        if best_exact >= 1.0:
            solved_gen = gen
            break
        elite = [t for _g, t in scored[: max(2, pop // 6)]]
        population = list(elite)
        while len(population) < pop:
            population.append(_bounded_meta(
                mutate_meta(rng.choice(elite), vars_, rng, **kw), vars_, rng, ops))
    return {"solved": best_exact >= 1.0, "fitness": round(best_exact, 4),
            "program": od.to_source(best) if best else None, "tree": best,
            "generation": solved_gen, "generations_run": min(gen, generations),
            "evals": pop * min(gen, generations), "pop": pop}


# ===========================================================================
# GRID TASKS (the ARC connection) — flat grid in the "seq" family: g = xs (row-major), w = n (width).
# Reference outputs are manufactured by the SAME bounded routines the interpreter uses, so a correct
# grammar program reproduces the I/O EXACTLY (X4.1 external-verification discipline).
# ===========================================================================
def _ref_obj_size0(g: tuple, w: int) -> int:
    """Size of the connected object that touches cell 0 (4-connectivity, same colour)."""
    return len(od._reach_from(od._grid_adjacency(g, w), 0))


def _ref_obj_size0_ge3(g: tuple, w: int) -> int:
    return 1 if _ref_obj_size0(g, w) >= 3 else 0


def _ref_num_objects(g: tuple, w: int) -> int:
    """Number of connected components of filled cells (transitive-closure quotient)."""
    lab = od._component_labels(od._grid_adjacency(g, w))
    return sum(1 for i, m in enumerate(lab) if m == i)


def sample_grid_io(ref: Callable[[tuple, int], int], n: int, rng: random.Random, *,
                   plant_corner: bool = False) -> list[tuple[dict, Any]]:
    """Manufacture n distinct grid I/O examples. Grids are H x W (H,W in 2..4), cells 0/1 (occasionally a
    second colour 2 to force colour-separated components). `plant_corner` guarantees cell 0 is filled (so
    'object at cell 0' is well-defined for the size/ge3 tasks)."""
    out: list = []
    seen: set = set()
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        w = rng.randint(2, 4)
        h = rng.randint(2, 4)
        cells = []
        for idx in range(w * h):
            rr = rng.random()
            cells.append(0 if rr < 0.42 else (1 if rr < 0.86 else 2))
        if plant_corner:
            cells[0] = 1
        g = tuple(cells)
        key = (g, w)
        if key in seen:
            continue
        seen.add(key)
        out.append(({"xs": g, "n": w}, ref(g, w)))
    return out


GRID_TASKS = {
    "grid_obj_size0": {"ref": _ref_obj_size0, "plant": True,
                       "note": "size of the object touching cell 0 (reach o edges)"},
    "grid_obj_size0_ge3": {"ref": _ref_obj_size0_ge3, "plant": True,
                           "note": "DEPENDENT: is that object big (>=3)? — needs obj_size0 as a sub-step"},
    "grid_num_objects": {"ref": _ref_num_objects, "plant": False,
                         "note": "number of connected components (filter(_x==_i) o closure o edges)"},
}


# ===========================================================================
# DISCOVERY — self-invent a program for a task from I/O, over the enabled meta-basis. Reuses X1
# compression_progress as the learning-progress readout (novel-and-learnable == the frontier we want).
# ===========================================================================
def _replace_first(tree: Any, sub: Any, repl: Any, _done: list | None = None) -> Any:
    """Rebuild `tree` with the FIRST structural occurrence of `sub` replaced by `repl`."""
    _done = _done if _done is not None else [False]
    if not isinstance(tree, tuple) or not tree:
        return tree
    if not _done[0] and tree == sub:
        _done[0] = True
        return repl
    return tuple([tree[0]] + [_replace_first(c, sub, repl, _done) if isinstance(c, tuple) else c
                              for c in tree[1:]])


def simplify(tree: Any, tests: list, holdout: list | None = None) -> Any:
    """Generic parsimony polish: greedily replace a subtree with a STRICTLY smaller expression (one of its
    own children, or the constant 0/1) whenever that keeps EVERY example exact — a task-agnostic shrink
    (no answer injected) that returns a self-invented primitive in its minimal spelling, stripping the
    inert wrappers a stochastic search accretes. Correctness is re-verified on train (+ holdout) after
    every accepted shrink, so it can never change what the program computes."""
    def exact(t: Any) -> bool:
        if od.fitness(t, tests) < 1.0:
            return False
        return od.fitness(t, holdout) >= 1.0 if holdout else True

    if not exact(tree):
        return tree
    cur = tree
    changed = True
    while changed:
        changed = False
        for sub in list(od._subtrees(cur)):
            if not (isinstance(sub, tuple) and len(sub) > 1):
                continue
            repls = [c for c in sub[1:] if isinstance(c, tuple)] + [("int", 0), ("int", 1)]
            for repl in repls:
                if od._size(repl) >= od._size(sub):
                    continue
                cand = _replace_first(cur, sub, repl)
                if od._size(cand) < od._size(cur) and exact(cand):
                    cur = cand
                    changed = True
                    break
            if changed:
                break
    return cur


def discover(tests: list, vars_: list[str], *, ops: tuple, seeds: list[int], pop: int = 160,
             generations: int = 300, depth: int = 4, library: tuple = (), primitives: tuple = (),
             holdout: list | None = None) -> dict:
    """Run evolve_meta across `seeds`; return the first exact-and-generalising discovery with its stats.
    A discovery must pass a held-out battery (generalisation, not overfit) to count."""
    from packages.evolution import compression_progress as _cp
    attempts = []
    for s in seeds:
        res = evolve_meta(tests, vars_, ops=ops, pop=pop, generations=generations, rng_seed=s,
                          depth=depth, library=library, primitives=primitives)
        gen_ok = True
        if res["tree"] is not None and holdout:
            gen_ok = od.fitness(res["tree"], holdout) >= 1.0
        lp = 0.0
        if res["tree"] is not None:
            try:
                lp = _cp.compression_progress(res["tree"], list(library), ())
            except Exception:
                lp = 0.0
        tree = res["tree"]
        program = res["program"]
        if res["solved"] and gen_ok and tree is not None:                 # minimal-spelling polish
            tree = simplify(tree, tests, holdout)
            program = od.to_source(tree)
            try:
                lp = _cp.compression_progress(tree, list(library), ())
            except Exception:
                pass
        attempts.append({"seed": s, "solved": res["solved"], "generalises": gen_ok,
                         "program": program, "evals": res["evals"],
                         "generation": res["generation"], "learning_progress": round(lp, 4),
                         "tree": tree})
        if res["solved"] and gen_ok:
            return {"discovered": True, "winner": attempts[-1], "attempts": attempts}
    return {"discovered": False, "winner": None, "attempts": attempts}


def promote_discovered(state: dict, family: str, tree: Any) -> bool:
    """Promote a discovered program into the solver's NAMED-primitive vocabulary (X4.2 path): variabilise
    the family's primary input into a shared hole and gate for non-degeneracy. Once promoted, a dependent
    task can instantiate the invented KIND in a single step — the causal-compounding channel."""
    state.setdefault("promoted", {f: [] for f in od._FAMILIES})
    return od._promote_primitive(state, family, tree)


def promoted_primitives(state: dict, family: str) -> tuple:
    return tuple({"template": p["template"], "arity": p["arity"]}
                 for p in state.get("promoted", {}).get(family, ()))
