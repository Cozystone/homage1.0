# -*- coding: utf-8 -*-
"""OPEN-ENDED synthesis domain for the self-acceleration (owner signal 4) re-measurement.

WHY THIS FILE EXISTS
--------------------
The prior signal-4 measurement ran in the TOY arithmetic/list domain (`code_evolver` +
`auto_curriculum`, families 'ab' scalars and 'xs' int-lists). It measured NEGATIVE: the
cumulative-distinct curve was concave (a2 < 0), per-round-new slope < 0, compute-efficiency
late/early < 1 — saturating self-improvement, not self-acceleration. The invention->solver loop
was CLOSED and it STILL saturated. The honest diagnosis was DOMAIN FINITENESS: the toy
interpreter's reachable-function set is tiny (2 scalars or short int-lists, 5 arithmetic ops, one
conditional, one fold) and is exhausted within ~15 distinct functions.

This module tests that diagnosis by enlarging the reachable-function set BY ORDERS OF MAGNITUDE,
then re-running the SAME rigorous protocol. It is a fresh, self-contained interpreter — it does NOT
modify `code_evolver.evaluate` (which is int-only and covered by the committed test suite). It reuses
the grammar-agnostic anti-unification machinery from `abstraction.py` for primitive invention.

WHAT MAKES IT (MUCH) MORE OPEN-ENDED THAN THE TOY DOMAIN
-------------------------------------------------------
1. RICHER VALUE TYPES: not just int. Values are int | str | tuple (immutable list). Programs can
   output numbers, strings, or nested sequences — so the behavioral-signature space is combinatorial
   in the value lattice, not a small integer range.
2. RECURSION / UNBOUNDED CONSTRUCTION: two bounded-fixpoint combinators — `iter` (apply a step N
   times: structural recursion / accumulation) and `build` (UNFOLD: grow a length-N sequence from a
   seed: anamorphism). With a tuple state these express Fibonacci-like and list-generating functions.
   This is the qualitative jump: the reachable set is unbounded in principle (grow-a-list-of-N-of-X),
   not a fixed finite table.
3. MUCH LARGER PRIMITIVE SET: ~22 combinators (add sub mul idiv mod cat rep len get slice rev upper
   lower ord chr range map filter reduce iter build if) vs the toy's ~7, plus arbitrary-body
   higher-order forms (reduce/map/filter/iter/build take EXPRESSION bodies over _x/_acc/_i, not a
   fixed operator symbol).
4. MORE FAMILIES with cross-type inputs: 'num' (two ints), 'text' (str + int), 'seq' (int-list + int).

SAFETY (identical discipline to the toy kernel)
-----------------------------------------------
Every value is produced by an INTERPRETER over a whitelisted tuple-tree grammar — never `exec`/`eval`
/`compile`. The interpreter is TOTAL (no candidate can raise: every op guards its own type/zero/empty
cases) and BOUNDED (a per-evaluation FUEL counter plus hard caps on sequence length and iteration
count guarantee termination and bounded memory, so nested `build`/`iter` can never blow up). An
evolved candidate can only ever shuffle ints/strings/tuples within these caps.
"""
from __future__ import annotations

import os
import random
from typing import Any, Callable

from packages.evolution import egraph_abstraction as _egraph
from packages.evolution.abstraction import (
    anti_unify,
    canonical,
    compression_gain,
    holes_in,
    instantiate as _instantiate,
    match as _match,
)

# ---------------------------------------------------------------------------
# Hard safety bounds — termination + bounded memory. Nested build/iter cannot escape these.
# ---------------------------------------------------------------------------
MAX_LEN = 32          # cap on any string / sequence length
MAX_ITER = 16         # cap on rep / iter / build iteration count
FUEL = 4000           # node-evaluations budget per top-level evaluate() call
_INT_CLAMP = 10 ** 7  # keep integers bounded so arithmetic stays cheap
MAX_NODES = 100       # hard cap on a program-tree's node count (bounds depth -> bounds recursion of
#                       every structural pass: _ev / to_source / _size / mutate; prevents the
#                       compose/primitive-wrap in mutate from growing a lineage without bound).


def _too_big(t: Any, cap: int = MAX_NODES) -> bool:
    """Iterative (stack-safe) node-count test: True if the tree exceeds `cap` nodes. Never recurses,
    so it stays safe even on the pathological deep trees it exists to reject."""
    stack, n = [t], 0
    while stack:
        x = stack.pop()
        if isinstance(x, tuple) and x:
            n += 1
            if n > cap:
                return True
            stack.extend(c for c in x[1:] if isinstance(c, tuple))
    return False

# Body-variable names bound INSIDE higher-order forms (never appear in a family's probe env).
_X, _I, _ACC = "_x", "_i", "_acc"

# --- X4.3 META-BASIS constants (the generative substrate; see meta_basis.py) --------------------------
# The recursion parameter is a FRESH name, distinct from _x/_i/_acc, so a recursive call can carry the
# OUTER loop element inward — this is what breaks the single-bound-variable ceiling that made nested
# comparison (second-largest, sort) unreachable in the base grammar.
_R = "_r"
_FIXBODY = "__fixbody__"           # reserved env keys carrying the active fix body + its recursion depth
_FIXDEPTH = "__fixdepth__"
MAX_REC = 64                       # hard recursion-depth cap (belt-and-suspenders with FUEL; real depth
#                                    on the tiny task inputs is <= ~10, so it never truncates a correct
#                                    program — it only guarantees termination on a pathological candidate).

# --- X4.4 additive EXTENSION-OP registry (the scheme-synthesis hook) ----------------------------------
# A key -> handler(t, env, fuel, ev) map, consulted by _ev ONLY for a key no built-in branch matched
# (i.e. a key that today returns 0). It is EMPTY by default, so evaluate() is byte-identical; and even
# once populated (packages.evolution.scheme_synthesis registers fold_s/para_s/unfold_s/unit on import) it
# can only ADD behaviour for keys the base grammar NEVER emits — a base program is unaffected either way.
# Handlers stay fuel-bounded (they receive `ev` and the shared fuel list; the recursion schemes decrement
# it per element exactly like map/reduce), so the total-termination guarantee is preserved.
_EXT_OPS: dict[str, Callable[..., Any]] = {}


# ===========================================================================
# TOTAL, FUEL-BOUNDED INTERPRETER  (int | str | tuple)
# ===========================================================================
def _clamp_int(n: int) -> int:
    if n > _INT_CLAMP:
        return _INT_CLAMP
    if n < -_INT_CLAMP:
        return -_INT_CLAMP
    return n


def _as_int(v: Any) -> int:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return len(v)
    if isinstance(v, tuple):
        return len(v)
    return 0


def _as_str(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, tuple):
        return "".join(_as_str(x) for x in v)[:MAX_LEN]
    return ""


def _as_seq(v: Any) -> tuple:
    if isinstance(v, tuple):
        return v
    if isinstance(v, str):
        return tuple(v)
    return ()


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    return len(v) > 0 if isinstance(v, (str, tuple)) else False


_CMP: dict[str, Callable[[Any, Any], bool]] = {
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "!=": lambda a, b: a != b,
}


# ===========================================================================
# X4.3 META-BASIS helpers — safe, total, fuel-/depth-bounded relational & recursion substrate. These
# are the FUNDAMENTAL operations (ordering, bounded fixpoint, adjacency, transitive closure) over which
# the engine INVENTS new domain primitive KINDS (sort/dedup/segmentation). They are never exec/eval'd —
# pure Python over int|str|tuple, dispatched only when a program tree carries the corresponding key.
# ===========================================================================
def _meta_order(a: Any, b: Any, take_min: bool) -> Any:
    """Ordering pick for min2/max2. Comparable exactly like `cmp`: same-type (or int/int) compares
    directly, else by integer projection; a tie keeps the first operand (stable)."""
    try:
        if type(a) is type(b) or (isinstance(a, int) and isinstance(b, int)):
            first_le = a <= b
        else:
            first_le = _as_int(a) <= _as_int(b)
    except Exception:
        first_le = True
    lo, hi = (a, b) if first_le else (b, a)
    return lo if take_min else hi


def _apply_fix(body: Any, argval: Any, env: dict, fuel: list, depth: int) -> Any:
    """Apply a fix body to argval, binding the recursion parameter _r. Termination is DOUBLY bounded: the
    global fuel budget (shared with every node-eval) AND an explicit depth cap. When either trips, return
    the current argument (a total, safe base case) rather than recursing. Non-tail recursion is supported:
    a `rec` node evaluates wherever it appears and its value flows into the enclosing expression."""
    fuel[0] -= 1
    if fuel[0] <= 0 or depth > MAX_REC:
        return argval
    return _ev(body, {**env, _R: argval, _FIXBODY: body, _FIXDEPTH: depth}, fuel)


def _grid_adjacency(g: Any, w: int) -> tuple:
    """Pairwise 4-neighbour adjacency of a FLAT grid `g` (row-major, width `w`). adj[i] lists the indices
    that are up/down/left/right of i AND share i's colour AND are non-background (value != 0); a filled
    cell is REFLEXIVELY in its own list (so an isolated filled cell is distinguishable from background),
    a background cell gets (). The fundamental relational op the engine composes into segmentation."""
    seq = g if isinstance(g, tuple) else _as_seq(g)
    n = len(seq)
    w = max(0, min(n, w))
    if n == 0 or w == 0:
        return tuple(() for _ in range(n))
    filled = [(_as_int(v) != 0) for v in seq]
    out = []
    for i in range(n):
        if not filled[i]:
            out.append(())
            continue
        _r_, c = divmod(i, w)
        nb = [i]                                             # reflexive: a filled cell is in its component
        if c + 1 < w and i + 1 < n and filled[i + 1] and seq[i + 1] == seq[i]:
            nb.append(i + 1)
        if c - 1 >= 0 and filled[i - 1] and seq[i - 1] == seq[i]:
            nb.append(i - 1)
        if i + w < n and filled[i + w] and seq[i + w] == seq[i]:
            nb.append(i + w)
        if i - w >= 0 and filled[i - w] and seq[i - w] == seq[i]:
            nb.append(i - w)
        out.append(tuple(nb))
    return tuple(out)


def _reach_from(adj: Any, src: int) -> tuple:
    """Transitive closure from `src` over adjacency `adj`: the sorted tuple of node indices reachable from
    src (iterative BFS, each node enqueued once -> bounded by N). Background/out-of-range src -> ()."""
    if not isinstance(adj, tuple):
        return ()
    n = len(adj)
    if n == 0 or src < 0 or src >= n or not adj[src]:
        return ()
    seen: set = set()
    stack = [src]
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        row = adj[x] if 0 <= x < n and isinstance(adj[x], tuple) else ()
        for y in row:
            if isinstance(y, int) and 0 <= y < n and y not in seen:
                stack.append(y)
    return tuple(sorted(seen))


def _component_labels(adj: Any) -> tuple:
    """Connected-component labelling (the transitive-closure quotient): labels[i] = the SMALLEST index in
    i's component for a filled cell, else -1 for background. Number-of-objects is then the count of i with
    labels[i] == i (each component has exactly one such root)."""
    if not isinstance(adj, tuple):
        return ()
    n = len(adj)
    labels = [-1] * n
    for s in range(n):
        if not adj[s] or labels[s] != -1:
            continue
        comp, seen, stack = [], set(), [s]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            row = adj[x] if isinstance(adj[x], tuple) else ()
            for y in row:
                if isinstance(y, int) and 0 <= y < n and y not in seen:
                    stack.append(y)
        m = min(comp)
        for x in comp:
            labels[x] = m
    return tuple(labels)


def evaluate(tree: Any, env: dict[str, Any]) -> Any:
    """Interpret a program tree over env, returning an int | str | tuple. Total (never raises) and
    fuel-bounded (terminates). A fresh fuel budget per top-level call; nested forms share it."""
    return _ev(tree, env, [FUEL])


def _ev(t: Any, env: dict[str, Any], fuel: list) -> Any:
    fuel[0] -= 1
    if fuel[0] <= 0 or not isinstance(t, tuple) or not t:
        return 0
    k = t[0]
    # --- leaves ---
    if k == "int":
        return t[1]
    if k == "str":
        return t[1]
    if k == "var":
        return env.get(t[1], 0)
    # --- numeric (coerce operands to int) ---
    if k in ("add", "sub", "mul", "idiv", "mod"):
        a = _as_int(_ev(t[1], env, fuel))
        b = _as_int(_ev(t[2], env, fuel))
        if k == "add":
            return _clamp_int(a + b)
        if k == "sub":
            return _clamp_int(a - b)
        if k == "mul":
            return _clamp_int(a * b)
        if k == "idiv":
            return a // b if b != 0 else 0
        return a % b if b != 0 else 0
    # --- polymorphic sequence / string ---
    if k == "cat":
        a = _ev(t[1], env, fuel)
        b = _ev(t[2], env, fuel)
        if isinstance(a, str) or isinstance(b, str):
            return (_as_str(a) + _as_str(b))[:MAX_LEN]
        if isinstance(a, tuple) or isinstance(b, tuple):
            return (_as_seq(a) + _as_seq(b))[:MAX_LEN]
        return (_as_str(a) + _as_str(b))[:MAX_LEN]          # two ints -> digit string
    if k == "rep":
        a = _ev(t[1], env, fuel)
        n = max(0, min(MAX_ITER, _as_int(_ev(t[2], env, fuel))))
        if isinstance(a, tuple):
            return (a * n)[:MAX_LEN]
        return (_as_str(a) * n)[:MAX_LEN]
    if k == "len":
        v = _ev(t[1], env, fuel)
        return len(v) if isinstance(v, (str, tuple)) else _as_int(v)
    if k == "get":
        v = _ev(t[1], env, fuel)
        i = _as_int(_ev(t[2], env, fuel))
        seq = v if isinstance(v, (str, tuple)) else _as_str(v)
        if not seq:
            return 0
        return seq[i % len(seq)]
    if k == "slice":
        v = _ev(t[1], env, fuel)
        i = _as_int(_ev(t[2], env, fuel))
        j = _as_int(_ev(t[3], env, fuel))
        seq = v if isinstance(v, (str, tuple)) else _as_str(v)
        n = len(seq)
        if n == 0:
            return seq
        i, j = max(-n, min(n, i)), max(-n, min(n, j))
        return seq[i:j]
    if k == "rev":
        v = _ev(t[1], env, fuel)
        if isinstance(v, str):
            return v[::-1]
        if isinstance(v, tuple):
            return v[::-1]
        return v
    if k in ("upper", "lower"):
        s = _as_str(_ev(t[1], env, fuel))
        return s.upper() if k == "upper" else s.lower()
    if k == "ord":
        v = _ev(t[1], env, fuel)
        if isinstance(v, str) and v:
            return ord(v[0])
        return _as_int(v)
    if k == "chr":
        n = _as_int(_ev(t[1], env, fuel))
        return chr(ord("a") + (n % 26))
    if k == "range":
        n = max(0, min(MAX_LEN, _as_int(_ev(t[1], env, fuel))))
        return tuple(range(n))
    # --- higher-order (bodies reference _x/_i/_acc) ---
    if k == "map":
        _, body, src = t
        seq = _as_seq(_ev(src, env, fuel))[:MAX_LEN]
        out = []
        for i, x in enumerate(seq):
            if fuel[0] <= 0:
                break
            out.append(_ev(body, {**env, _X: x, _I: i}, fuel))
        return tuple(out)
    if k == "filter":
        _, cond, src = t
        seq = _as_seq(_ev(src, env, fuel))[:MAX_LEN]
        out = []
        for i, x in enumerate(seq):
            if fuel[0] <= 0:
                break
            if _as_bool(_ev(cond, {**env, _X: x, _I: i}, fuel)):
                out.append(x)
        return tuple(out)
    if k == "reduce":
        _, body, init, src = t
        acc = _ev(init, env, fuel)
        for x in _as_seq(_ev(src, env, fuel))[:MAX_LEN]:
            if fuel[0] <= 0:
                break
            acc = _ev(body, {**env, _ACC: acc, _X: x}, fuel)
        return acc
    if k == "iter":                                          # apply step N times (structural recursion)
        _, step, seed, cnt = t
        acc = _ev(seed, env, fuel)
        n = max(0, min(MAX_ITER, _as_int(_ev(cnt, env, fuel))))
        for _ in range(n):
            if fuel[0] <= 0:
                break
            acc = _ev(step, {**env, _ACC: acc}, fuel)
        return acc
    if k == "build":                                         # UNFOLD: grow length-N seq from a seed
        _, step, seed, cnt = t
        acc = _ev(seed, env, fuel)
        n = max(1, min(MAX_LEN, _as_int(_ev(cnt, env, fuel))))
        out = [acc]
        for _ in range(n - 1):
            if fuel[0] <= 0:
                break
            acc = _ev(step, {**env, _ACC: acc}, fuel)
            out.append(acc)
        return tuple(out)[:MAX_LEN]
    if k == "if":
        _, cond, a, b = t
        return _ev(a, env, fuel) if _as_bool(_ev(cond, env, fuel)) else _ev(b, env, fuel)
    if k == "cmp":
        _, op, a, b = t
        va, vb = _ev(a, env, fuel), _ev(b, env, fuel)
        try:
            if type(va) is type(vb) or (isinstance(va, int) and isinstance(vb, int)):
                return _CMP[op](va, vb)
            return _CMP[op](_as_int(va), _as_int(vb))
        except Exception:
            return False
    # -----------------------------------------------------------------------------------------------
    # X4.3 META-BASIS (additive) — every branch below dispatches on a key the BASE grammar never emits
    # (min2/max2/fix/rec/edges/reach/closure), so a program that predates the meta-basis is byte-identical
    # (this block is dead for it). This is the generative substrate the engine invents new KINDS over.
    # -----------------------------------------------------------------------------------------------
    if k == "min2" or k == "max2":                           # ordering primitives
        a = _ev(t[1], env, fuel)
        b = _ev(t[2], env, fuel)
        return _meta_order(a, b, k == "min2")
    if k == "fix":                                           # bounded self-reference (fresh param _r)
        _, body, arg = t
        return _apply_fix(body, _ev(arg, env, fuel), env, fuel, 0)
    if k == "rec":                                           # recursive self-call inside a fix body
        body = env.get(_FIXBODY)
        if body is None:
            return 0                                         # a `rec` outside any `fix` is inert
        return _apply_fix(body, _ev(t[1], env, fuel), env, fuel, env.get(_FIXDEPTH, 0) + 1)
    if k == "edges":                                         # relational: pairwise same-colour adjacency
        g = _ev(t[1], env, fuel)
        w = _as_int(_ev(t[2], env, fuel))
        return _grid_adjacency(g, w)
    if k == "reach":                                         # relational: transitive closure from a source
        adj = _ev(t[1], env, fuel)
        src = _as_int(_ev(t[2], env, fuel))
        return _reach_from(adj, src)
    if k == "closure":                                       # relational: connected-component labelling
        return _component_labels(_ev(t[1], env, fuel))
    # X4.4 additive extension hook: dispatch a registered scheme op (fold_s/para_s/unfold_s/unit). Reached
    # only for a key the built-ins never matched, so this is inert for every base/meta program above.
    ext = _EXT_OPS.get(k)
    if ext is not None:
        return ext(t, env, fuel, _ev)
    return 0


# ---------------------------------------------------------------------------
# Rendering (readable source for logs + source-dedup of invented primitives)
# ---------------------------------------------------------------------------
def to_source(t: Any) -> str:
    if not isinstance(t, tuple) or not t:
        return repr(t)
    k = t[0]
    if k == "int":
        return str(t[1])
    if k == "str":
        return repr(t[1])
    if k == "var":
        return str(t[1])
    if k == "hole":
        return f"?{t[1]}"
    if k in ("add", "sub", "mul", "idiv", "mod"):
        sym = {"add": "+", "sub": "-", "mul": "*", "idiv": "//", "mod": "%"}[k]
        return f"({to_source(t[1])} {sym} {to_source(t[2])})"
    if k == "cat":
        return f"cat({to_source(t[1])}, {to_source(t[2])})"
    if k == "rep":
        return f"rep({to_source(t[1])}, {to_source(t[2])})"
    if k in ("len", "rev", "upper", "lower", "ord", "chr", "range"):
        return f"{k}({to_source(t[1])})"
    if k == "get":
        return f"get({to_source(t[1])}, {to_source(t[2])})"
    if k == "slice":
        return f"slice({to_source(t[1])}, {to_source(t[2])}, {to_source(t[3])})"
    if k == "map":
        return f"map({to_source(t[1])}, {to_source(t[2])})"
    if k == "filter":
        return f"filter({to_source(t[1])}, {to_source(t[2])})"
    if k == "reduce":
        return f"reduce({to_source(t[1])}, {to_source(t[2])}, {to_source(t[3])})"
    if k == "iter":
        return f"iter({to_source(t[1])}, {to_source(t[2])}, {to_source(t[3])})"
    if k == "build":
        return f"build({to_source(t[1])}, {to_source(t[2])}, {to_source(t[3])})"
    if k == "if":
        return f"({to_source(t[2])} if {to_source(t[1])} else {to_source(t[3])})"
    if k == "cmp":
        return f"({to_source(t[2])} {t[1]} {to_source(t[3])})"
    # X4.3 meta-basis rendering (additive)
    if k in ("min2", "max2", "edges", "reach"):
        return f"{k}({to_source(t[1])}, {to_source(t[2])})"
    if k == "fix":
        return f"fix({to_source(t[1])}, {to_source(t[2])})"
    if k == "rec":
        return f"rec({to_source(t[1])})"
    if k == "closure":
        return f"closure({to_source(t[1])})"
    # X4.4 recursion-scheme rendering (additive; keeps source-dedup of promoted primitives exact)
    if k == "unit":
        return f"unit({to_source(t[1])})"
    if k in ("fold_s", "para_s", "unfold_s"):
        return f"{k}({', '.join(to_source(c) for c in t[1:])})"
    return f"{k}(...)"


# ===========================================================================
# GRAMMAR GENERATORS — random_tree + mutate  (library + invented-primitive aware)
# ===========================================================================
_NUM_OPS = ("add", "sub", "mul", "idiv", "mod")
_STR_CONSTS = ("a", "b", "c", "ab", "xy")


def _leaf(vars_: list[str], rng: random.Random) -> Any:
    r = rng.random()
    if vars_ and r < 0.6:
        return ("var", rng.choice(vars_))
    if r < 0.8:
        return ("int", rng.randint(0, 5))
    return ("str", rng.choice(_STR_CONSTS))


def _template_arity(template: Any) -> int:
    acc: set = set()

    def walk(t: Any) -> None:
        if isinstance(t, tuple) and t:
            if t[0] == "hole":
                acc.add(t[1])
            else:
                for c in t[1:]:
                    if isinstance(c, tuple):
                        walk(c)

    walk(template)
    return len(acc)


def _grow_primitive(prim: Any, vars_: list[str], rng: random.Random, depth: int, **kw: Any) -> Any:
    tmpl = prim["template"] if isinstance(prim, dict) else prim
    arity = (prim.get("arity") if isinstance(prim, dict) else None) or _template_arity(tmpl)
    # Grow arguments WITHOUT further primitives and at strictly-decreasing depth (may reach 0 -> leaf).
    # This is the termination guarantee: without it, a primitive's arg could instantiate another
    # primitive at a depth floored to 1, looping primitive-in-primitive without bound.
    akw = dict(kw)
    akw["primitives"] = ()
    args = [random_tree(vars_, rng, max(0, depth - 1), **akw) for _ in range(max(1, arity))]
    return _instantiate(tmpl, args)


def random_tree(vars_: list[str], rng: random.Random, depth: int = 3, *,
                library: tuple = (), primitives: tuple = ()) -> Any:
    """A random program tree of at most `depth`. Leaves are vars/consts, or a whole reusable
    sub-program from `library` (the compositional prior), or an instance of an INVENTED primitive
    (the self-expanded vocabulary). Internal nodes draw from the full ~22-combinator grammar,
    including the recursion forms map/filter/reduce/iter/build."""
    kw = dict(library=library, primitives=primitives)
    if depth <= 0 or rng.random() < 0.32:
        if primitives and rng.random() < 0.22:
            return _grow_primitive(rng.choice(primitives), vars_, rng, depth, **kw)
        if library and rng.random() < 0.4:
            return rng.choice(library)
        return _leaf(vars_, rng)
    sub = lambda: random_tree(vars_, rng, depth - 1, **kw)  # noqa: E731
    ev = vars_ + [_X, _I, _ACC]                              # element/index/acc visible in bodies
    subv = lambda: random_tree(ev, rng, depth - 1, **kw)    # noqa: E731
    r = rng.random()
    if r < 0.34:                                             # numeric op
        return (rng.choice(_NUM_OPS), sub(), sub())
    if r < 0.46:                                             # string / sequence builders
        return rng.choice([
            ("cat", sub(), sub()), ("rep", sub(), sub()), ("rev", sub()),
            ("upper", sub()), ("lower", sub()), ("chr", sub()), ("range", sub()),
        ])
    if r < 0.58:                                             # accessors
        return rng.choice([
            ("len", sub()), ("get", sub(), sub()), ("slice", sub(), sub(), sub()), ("ord", sub()),
        ])
    if r < 0.74:                                             # higher-order over sequences
        return rng.choice([
            ("map", subv(), sub()),
            ("filter", ("cmp", rng.choice(list(_CMP)), subv(), subv()), sub()),
            ("reduce", subv(), sub(), sub()),
        ])
    if r < 0.88:                                             # recursion / unbounded construction
        return rng.choice([
            ("iter", subv(), sub(), sub()),
            ("build", subv(), sub(), sub()),
        ])
    return ("if", ("cmp", rng.choice(list(_CMP)), sub(), sub()), sub(), sub())


def _subtrees(t: Any):
    if isinstance(t, tuple) and t:
        yield t
        for c in t[1:]:
            if isinstance(c, tuple):
                yield from _subtrees(c)


def mutate(tree: Any, vars_: list[str], rng: random.Random, *,
           library: tuple = (), primitives: tuple = ()) -> Any:
    """One local edit: retype a leaf, tweak a constant, flip an operator, regrow a small subtree,
    COMPOSE the whole program with a library building block, or BUILD with an invented primitive —
    the failing verifier examples are the symbolic 'gradient' selection follows."""
    kw = dict(library=library, primitives=primitives)
    if not isinstance(tree, tuple) or not tree:
        return random_tree(vars_, rng, 2, **kw)
    k = tree[0]
    r = rng.random()
    big = _too_big(tree)                                     # stop unbounded depth growth in a lineage
    if library and not big and r < 0.14:                    # compose with a solved sub-program
        return (rng.choice(_NUM_OPS + ("cat",)), tree, rng.choice(library))
    if primitives and r < 0.24:                              # build with an invented primitive
        inst = _grow_primitive(rng.choice(primitives), vars_, rng, 2, **kw)
        if big or rng.random() < 0.5:
            return inst                                     # replace (never grows the tree)
        return (rng.choice(_NUM_OPS + ("cat",)), tree, inst)
    if k in ("int",):
        return ("int", max(0, tree[1] + rng.choice([-2, -1, 1, 2])))
    if k == "str":
        return ("str", rng.choice(_STR_CONSTS))
    if k == "var":
        if rng.random() < 0.5 and vars_:
            return ("var", rng.choice(vars_))
        return random_tree(vars_, rng, 1, **kw)
    if k == "cmp":
        if rng.random() < 0.5:
            return ("cmp", rng.choice(list(_CMP)), tree[2], tree[3])
        return ("cmp", tree[1], mutate(tree[2], vars_, rng, **kw), tree[3])
    if k in ("add", "sub", "mul", "idiv", "mod"):
        if r < 0.4:
            return (rng.choice(_NUM_OPS), tree[1], tree[2])  # flip operator
        if rng.random() < 0.5:
            return (k, mutate(tree[1], vars_, rng, **kw), tree[2])
        return (k, tree[1], mutate(tree[2], vars_, rng, **kw))
    # generic node: recurse into a random child, or regrow it
    idx = [i for i in range(1, len(tree)) if isinstance(tree[i], tuple)]
    if idx and rng.random() < 0.85:
        i = rng.choice(idx)
        ev = vars_ + [_X, _I, _ACC]
        child = mutate(tree[i], ev, rng, **kw) if rng.random() < 0.6 else random_tree(ev, rng, 2, **kw)
        return tuple(list(tree[:i]) + [child] + list(tree[i + 1:]))
    return random_tree(vars_, rng, 2, **kw)


# ===========================================================================
# VERIFIER FITNESS  (exact + smoothed, type-aware)
# ===========================================================================
def _similar(got: Any, want: Any) -> float:
    """Type-aware closeness in [0,1) for near-misses (a symbolic gradient over the value lattice)."""
    if type(got) is not type(want):
        # partial credit only if numeric-comparable
        if isinstance(got, int) and isinstance(want, int):
            return 1.0 / (1.0 + abs(got - want))
        return 0.0
    if isinstance(want, int):
        return 1.0 / (1.0 + abs(got - want))
    if isinstance(want, str):
        if not want:
            return 0.0
        common = sum(1 for a, b in zip(got, want) if a == b)
        return 0.9 * common / max(len(want), len(got), 1)
    if isinstance(want, tuple):
        if not want:
            return 0.0
        common = sum(1 for a, b in zip(got, want) if a == b)
        return 0.9 * common / max(len(want), len(got), 1)
    return 0.0


def fitness(tree: Any, tests: list) -> float:
    """Exact verifier: fraction of input->output examples satisfied EXACTLY. Correctness gate."""
    if not tests:
        return 0.0
    ok = sum(1 for env, want in tests if evaluate(tree, env) == want)
    return ok / len(tests)


def graded_fitness(tree: Any, tests: list) -> float:
    """Smoothed verifier for SEARCH: exact hits dominate; near-misses earn type-aware partial credit."""
    if not tests:
        return 0.0
    exact, close = 0, 0.0
    for env, want in tests:
        got = evaluate(tree, env)
        if got == want:
            exact += 1
        else:
            close += _similar(got, want)
    n = len(tests)
    return exact / n + 0.25 * (close / n)


def _bounded(tree: Any, vars_: list[str], rng: random.Random, kw: dict) -> Any:
    """Keep every population member within MAX_NODES: an oversized candidate is discarded and replaced
    by a fresh small tree, so no lineage can accumulate unbounded depth across generations."""
    if _too_big(tree):
        return random_tree(vars_, rng, 3, **kw)
    return tree


def evolve(tests: list, vars_: list[str], *, pop: int = 80, generations: int = 100,
           rng_seed: int = 7, library: tuple = (), primitives: tuple = (), log=None) -> dict:
    """Gradient-free program search over the open-ended grammar: a population of trees ranked by the
    smoothed verifier, elitism + mutated offspring, until a candidate passes every example EXACTLY (or
    the budget ends). `library` supplies solved sub-programs as reusable leaves; `primitives` are
    invented templates the search may instantiate. Returns the best program and compute spent."""
    rng = random.Random(rng_seed)
    kw = dict(library=library, primitives=primitives)
    population = [_bounded(random_tree(vars_, rng, 3, **kw), vars_, rng, kw) for _ in range(pop)]
    best, best_exact, solved_gen, gen = None, -1.0, None, 0
    for gen in range(1, generations + 1):
        scored = sorted(((graded_fitness(t, tests), t) for t in population), key=lambda x: -x[0])
        for _g, t in scored[: max(4, pop // 8)]:
            e = fitness(t, tests)
            if e > best_exact:
                best_exact, best = e, t
        if best_exact >= 1.0:
            solved_gen = gen
            break
        elite = [t for _g, t in scored[: max(2, pop // 6)]]
        population = list(elite)
        while len(population) < pop:
            population.append(_bounded(mutate(rng.choice(elite), vars_, rng, **kw), vars_, rng, kw))
    return {"solved": best_exact >= 1.0, "fitness": round(best_exact, 4),
            "program": to_source(best) if best else None, "tree": best,
            "generation": solved_gen, "generations_run": min(gen, generations),
            "evals": pop * min(gen, generations)}


# ===========================================================================
# SELF-CURRICULUM over the open-ended domain (mirrors auto_curriculum, richer grammar)
# ===========================================================================
_FAMILIES: dict[str, dict[str, Any]] = {
    "num": {"vars_": ["a", "b"]},
    "text": {"vars_": ["s", "k"]},
    "seq": {"vars_": ["xs", "n"]},
}

_PROBES: dict[str, list[dict[str, Any]]] = {
    "num": [{"a": a, "b": b} for a, b in
            [(0, 0), (1, 0), (0, 1), (2, 3), (3, 2), (5, 1), (1, 5), (4, 4), (7, 2), (2, 7),
             (6, 3), (9, 1), (3, 8), (8, 0)]],
    "text": [{"s": s, "k": k} for s, k in
             [("", 0), ("a", 1), ("ab", 2), ("abc", 1), ("hello", 3), ("xy", 0), ("z", 4),
              ("cat", 2), ("abcd", 3), ("mn", 1), ("pqrs", 2), ("a", 3), ("bb", 2), ("code", 4)]],
    "seq": [{"xs": xs, "n": n} for xs, n in
            [((), 0), ((0,), 1), ((1, 2), 2), ((3, 1, 2), 1), ((4, 0, 4), 3), ((5,), 2),
             ((1, 2, 3, 4), 2), ((2, 2), 0), ((6, 1, 5), 4), ((0, 0, 0), 1), ((7, 3), 2),
             ((2, 4, 6, 8), 3), ((9,), 1), ((1, 3, 5, 7), 2)]],
}

# Seed axioms — compact, non-trivial starting programs per family. Everything past these is reached
# by composition/invention, not by a human adding a primitive.
_SEED_TREES: dict[str, list[tuple[str, Any]]] = {
    "num": [
        ("a+b", ("add", ("var", "a"), ("var", "b"))),
        ("a*a", ("mul", ("var", "a"), ("var", "a"))),
        ("max(a,b)", ("if", ("cmp", ">", ("var", "a"), ("var", "b")), ("var", "a"), ("var", "b"))),
    ],
    "text": [
        ("len(s)", ("len", ("var", "s"))),
        ("rev(s)", ("rev", ("var", "s"))),
        ("cat(s,s)", ("cat", ("var", "s"), ("var", "s"))),
    ],
    "seq": [
        ("len(xs)", ("len", ("var", "xs"))),
        ("sum(xs)", ("reduce", ("add", ("var", _ACC), ("var", _X)), ("int", 0), ("var", "xs"))),
        ("range(n)", ("range", ("var", "n"))),
    ],
}

_LIB_CAP = 60
_MAX_KEEP_SIZE = 40
_UP, _DOWN = 0.7, 0.34
_SATURATED = 0.2
_FAST = 0.5


def _size(tree: Any) -> int:
    if not isinstance(tree, (tuple, list)) or not tree:
        return 1
    return 1 + sum(_size(t) for t in tree[1:] if isinstance(t, (tuple, list)))


def signature(tree: Any, family: str) -> str:
    """Behavioral fingerprint: outputs over the fixed probe battery, joined stably. Capability identity
    independent of syntax — works across value types (int/str/tuple all repr to a stable string)."""
    return "|".join(repr(evaluate(tree, env)) for env in _PROBES[family])


def _is_trivial(tree: Any, family: str) -> bool:
    outs = [evaluate(tree, env) for env in _PROBES[family]]
    if len({repr(o) for o in outs}) <= 1:
        return True                                          # constant — computes nothing
    for v in _FAMILIES[family]["vars_"]:
        if outs == [env[v] for env in _PROBES[family]]:
            return True                                      # identity projection
    return False


def _sample_env(family: str, rng: random.Random) -> dict[str, Any]:
    if family == "num":
        return {"a": rng.randint(0, 9), "b": rng.randint(0, 9)}
    if family == "text":
        n = rng.randint(0, 6)
        s = "".join(rng.choice("abcdefghijklmnop") for _ in range(n))
        return {"s": s, "k": rng.randint(0, 5)}
    n = rng.randint(0, 6)
    return {"xs": tuple(rng.randint(0, 7) for _ in range(n)), "n": rng.randint(0, 5)}


def _tests_from_tree(tree: Any, family: str, n: int, rng: random.Random) -> list:
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 8:
        tries += 1
        env = _sample_env(family, rng)
        key = repr(sorted((k, repr(v)) for k, v in env.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append((env, evaluate(tree, env)))
    return out


def new_state() -> dict[str, Any]:
    return {"round": 0, "tier": 0,
            "libraries": {f: [] for f in _FAMILIES},
            "programs": {f: [] for f in _FAMILIES},
            "sigs": {f: [] for f in _FAMILIES},
            "abstractions": {f: [] for f in _FAMILIES},
            "history": [],
            "frontier": {"distinct_solved": 0, "compressions": 0, "invented_primitives": 0}}


def _admit(state: dict[str, Any], family: str, tree: Any) -> str:
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
        state["libraries"][family][i] = tree
        state["programs"][family][i] = src
        return "compressed"
    return "dup"


# ---------------------------------------------------------------------------
# INVENTION — anti-unify recurring motifs into parameterized primitives, gated for non-degeneracy.
# ---------------------------------------------------------------------------
_VALUE_TAGS = {"add", "sub", "mul", "idiv", "mod", "cat", "rep", "len", "get", "slice", "rev",
               "upper", "lower", "ord", "chr", "range", "map", "filter", "reduce", "iter", "build", "if"}


def _hole_occ(t: Any) -> int:
    if not isinstance(t, tuple) or not t:
        return 0
    if t[0] == "hole":
        return 1
    return sum(_hole_occ(c) for c in t[1:] if isinstance(c, tuple))


def _body_has_var(t: Any) -> bool:
    if not isinstance(t, tuple) or not t:
        return False
    if t[0] == "hole":
        return False
    if t[0] == "var":
        return True
    return any(_body_has_var(c) for c in t[1:] if isinstance(c, tuple))


def mine(library: list, *, top_k: int = 6, min_gain: int = 2, max_pool: int = 70) -> list[dict]:
    """Invent primitives by anti-unifying recurring subtree motifs (DreamCoder abstraction, no neural
    recognizer). Keep 1-2 hole templates that COMPRESS the library, rooted at a value-producing op,
    with no pinned variable — reusing the grammar-agnostic anti-unifier from abstraction.py."""
    pool: list = []
    for lib in library:
        for st in _subtrees(lib):
            if (isinstance(st, tuple) and st[0] in _VALUE_TAGS and 3 <= _size(st) <= 11
                    and not _hole_occ(st) and st not in pool):
                pool.append(st)
        if len(pool) >= max_pool:
            break
    seen: dict[str, dict] = {}
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            tmpl = canonical(anti_unify(pool[i], pool[j]))
            h = holes_in(tmpl)
            if not (1 <= h <= 2) or _size(tmpl) - _hole_occ(tmpl) < 2 or _body_has_var(tmpl):
                continue
            if not (isinstance(tmpl, tuple) and tmpl[0] in _VALUE_TAGS):
                continue
            gain = compression_gain(library, tmpl)
            if gain < min_gain:
                continue
            key = to_source(tmpl)
            if key not in seen or gain > seen[key]["gain"]:
                seen[key] = {"template": tmpl, "arity": h, "gain": gain, "source": key}
    return sorted(seen.values(), key=lambda d: -d["gain"])[:top_k]


def _hole_arg_pool(family: str) -> list[Any]:
    fam = _FAMILIES[family]
    pool: list[Any] = [("var", v) for v in fam["vars_"]]
    pool += [("int", 1), ("int", 2), ("str", "a")]
    return pool


def _atomic_signatures(family: str) -> set:
    atoms: list[Any] = [t for _n, t in _SEED_TREES[family]]
    for v in _FAMILIES[family]["vars_"]:
        atoms.append(("var", v))
    sigs: set = set()
    for a in atoms:
        try:
            sigs.add(signature(a, family))
        except Exception:
            pass
    return sigs


def _expands_reachable(template: Any, arity: int, family: str) -> bool:
    """Semantic non-degeneracy gate before a primitive may enter the SOLVER vocabulary: (G1) its
    output must genuinely DEPEND on its holes (not a vestigial parameter); (G2) it must reach at least
    one NON-TRIVIAL behavior that is not already an atom/seed signature (not an algebraic identity)."""
    if arity < 1:
        return False
    pool = _hole_arg_pool(family)
    if not pool:
        return False
    import itertools
    combos = list(itertools.product(pool, repeat=arity))[:16]
    all_sigs, nontrivial = set(), set()
    for combo in combos:
        inst = _instantiate(template, list(combo))
        try:
            s = signature(inst, family)
        except Exception:
            continue
        all_sigs.add(s)
        if not _is_trivial(inst, family):
            nontrivial.add(s)
    if len(all_sigs) < 2 or not nontrivial:
        return False
    if nontrivial.issubset(_atomic_signatures(family)):
        return False
    return True


def _solver_primitives(state: dict[str, Any], family: str) -> tuple:
    out, seen = [], set()
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


def compose_target(library: list[Any], family: str, tier: int, rng: random.Random,
                   abstractions: tuple = ()) -> Any:
    """Invent a NEW target by combining solved building blocks (biased to small, canonical blocks) with
    the interpreter. Higher tiers add operands and wrap in a higher-order/recursion form, so difficulty
    grows structurally. Invented primitives seed some targets — the engine building on its own motifs."""
    fam = _FAMILIES[family]
    blocks = sorted(library, key=_size)
    small = blocks[: max(3, len(blocks) // 2 + 1)] or blocks
    leaves = [("var", v) for v in fam["vars_"]] + [("int", rng.randint(1, 3)), ("str", rng.choice(_STR_CONSTS))]

    def pick() -> Any:
        if small and rng.random() < 0.7:
            return rng.choice(small)
        return rng.choice(leaves)

    if abstractions and rng.random() < 0.4:
        ab = rng.choice(abstractions)
        node = _instantiate(ab["template"], [pick() for _ in range(ab["arity"])])
        if tier >= 1 and rng.random() < 0.5:
            node = (rng.choice(_NUM_OPS + ("cat",)), node, pick())
        return node

    arity = 2 if tier < 2 else rng.choice([2, 2, 3])
    node = pick()
    for _ in range(arity - 1):
        node = (rng.choice(_NUM_OPS + ("cat", "rep")), node, pick())
    if tier >= 1 and rng.random() < 0.45:
        wrap = rng.choice(["map", "filter", "reduce", "iter", "build", "if"])
        if wrap == "map":
            node = ("map", ("add", ("var", _X), ("int", rng.randint(0, 3))), pick())
        elif wrap == "filter":
            node = ("filter", ("cmp", rng.choice(list(_CMP)), ("var", _X), ("int", rng.randint(0, 4))), pick())
        elif wrap == "reduce":
            node = ("reduce", (rng.choice(_NUM_OPS), ("var", _ACC), ("var", _X)), ("int", 0), pick())
        elif wrap == "iter":
            node = ("iter", (rng.choice(_NUM_OPS), ("var", _ACC), pick()), pick(), ("var", fam["vars_"][-1]))
        elif wrap == "build":
            node = ("build", (rng.choice(_NUM_OPS), ("var", _ACC), ("int", rng.randint(1, 2))),
                    pick(), ("var", fam["vars_"][-1]))
        else:
            v0 = fam["vars_"][0]
            node = ("if", ("cmp", rng.choice(list(_CMP)), ("var", v0), pick()), node, pick())
    return node


def autonomous_round(state: dict[str, Any], rng: random.Random, *, problems: int = 6,
                     close_loop: bool = True, invent: bool = True, freeze_lib: bool = False,
                     pop: int = 80, base_budget: int = 90) -> dict[str, Any]:
    """One self-driven round over the open-ended domain. `freeze_lib`/`invent`/`close_loop` are the
    ablation knobs the signal-4 harness flips: freeze_lib=True forbids admitting/reusing new blocks
    (frozen archive), invent=False disables primitive mining, close_loop=False keeps invented
    primitives out of the SOLVER vocabulary (open-loop baseline).

    X4.1 (owner 2026-07-23): when ATANOR_EXTERNAL_PROBLEMS is set, the TARGET STREAM is drawn from the
    EXTERNAL corpus (external_corpus) instead of self-composition — the same loop, the same admit/mine/
    library machinery, but the problems are REAL functions verified by I/O examples (not composed from
    solved blocks). Default OFF preserves the exact self-composed behaviour, so the ④ A/B is clean and
    the committed tests are byte-identical. Composable with X1/X2/X3 (read independently)."""
    if _external_on():
        return external_round(state, rng, problems=problems, close_loop=close_loop, invent=invent,
                              freeze_lib=freeze_lib, pop=pop, base_budget=base_budget)
    state["round"] += 1
    tier = state["tier"]
    attempts, solved_ok, admitted, compressed, details = 0, 0, 0, 0, []
    solver_prim_uses = 0
    round_evals = 0

    for family in _FAMILIES:
        lib = state["libraries"][family]
        abns = tuple(state["abstractions"].get(family, ()))
        solver_prims = _solver_primitives(state, family) if (close_loop and invent) else ()
        fam = _FAMILIES[family]
        budget = min(base_budget + 30 * tier, 240)

        # (1) bootstrap seeds
        for name, tree in _SEED_TREES[family]:
            if signature(tree, family) in state["sigs"][family]:
                continue
            if freeze_lib and state["sigs"][family]:
                continue                                     # frozen: no new admits after bootstrap
            attempts += 1
            train = _tests_from_tree(tree, family, 14, rng)
            holdout = _tests_from_tree(tree, family, 10, rng)
            res = evolve(train, fam["vars_"], library=tuple(lib), primitives=solver_prims,
                         pop=pop, generations=budget, rng_seed=rng.randint(1, 10_000))
            round_evals += res["evals"]
            acc = bool(res["solved"] and (fitness(res["tree"], holdout) >= 1.0 if res["tree"] else False))
            if acc:
                solved_ok += 1
                verdict = _admit(state, family, res["tree"])
                admitted += verdict == "new"
                compressed += verdict == "compressed"
                solver_prim_uses += _uses_primitive(res["tree"], solver_prims)
            details.append({"family": family, "kind": "seed", "name": name, "accepted": acc})

        # (2) compose new targets from what is solved, re-derive, keep the generalizers
        per_family = max(1, problems // len(_FAMILIES))
        for _ in range(per_family):
            if not lib:
                break
            target = compose_target(lib, family, tier, rng, abstractions=abns)
            attempts += 1
            train = _tests_from_tree(target, family, 14, rng)
            holdout = _tests_from_tree(target, family, 10, rng)
            res = evolve(train, fam["vars_"], library=tuple(lib), primitives=solver_prims,
                         pop=pop, generations=budget, rng_seed=rng.randint(1, 10_000))
            round_evals += res["evals"]
            acc = bool(res["solved"] and (fitness(res["tree"], holdout) >= 1.0 if res["tree"] else False))
            verdict = "reject"
            if acc and not freeze_lib:
                solved_ok += 1
                verdict = _admit(state, family, res["tree"])
                admitted += verdict == "new"
                compressed += verdict == "compressed"
                solver_prim_uses += _uses_primitive(res["tree"], solver_prims)
            elif acc:
                solved_ok += 1                               # solved but frozen: not admitted
            details.append({"family": family, "kind": "composed", "verdict": verdict,
                            "accepted": acc, "target": to_source(target)})

    # (3) invent primitives from each family library (unless ablated). X2: when ATANOR_EGRAPH_
    # ABSTRACTION is set, mine MODULO the equational theory (egraph_abstraction) with THIS domain's
    # value tags — the same tier-opening miner as auto_curriculum, adapted to open_domain's grammar
    # (opname,L,R). Default off = the naive syntactic miner, byte-identical baseline.
    invented = 0
    if invent and not freeze_lib:
        egraph_on = os.getenv("ATANOR_EGRAPH_ABSTRACTION", "0").strip().lower() not in (
            "", "0", "false", "no", "off")
        for family in _FAMILIES:
            if egraph_on:
                found = _egraph.mine(state["libraries"][family], top_k=6, min_gain=2,
                                     pool_tags=tuple(_VALUE_TAGS), size_hi=11,
                                     root_ok=lambda t: True, source_of=to_source)
            else:
                found = mine(state["libraries"][family], top_k=6, min_gain=2)
            state["abstractions"][family] = [
                {"template": a["template"], "arity": a["arity"], "source": a["source"], "gain": a["gain"]}
                for a in found]
            invented += len(found)

    competence = (solved_ok / attempts) if attempts else 0.0
    novelty = (admitted / attempts) if attempts else 0.0
    moved = "hold"
    if competence >= _UP and novelty < _SATURATED:
        state["tier"] = min(tier + 1, 6)
        moved = "up" if state["tier"] != tier else "hold"
    elif novelty >= _FAST:
        state["tier"] = min(tier + 1, 6)
        moved = "up" if state["tier"] != tier else "hold"
    elif competence < _DOWN and tier > 0:
        state["tier"] = tier - 1
        moved = "down"

    distinct = sum(len(s) for s in state["sigs"].values())
    sizes = [_size(t) for f in _FAMILIES for t in state["libraries"][f]]
    state["frontier"] = {"distinct_solved": distinct,
                         "compressions": state["frontier"].get("compressions", 0) + compressed,
                         "avg_size": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                         "invented_primitives": invented}
    rec = {"round": state["round"], "tier_before": tier, "tier_after": state["tier"], "move": moved,
           "attempts": attempts, "admitted": admitted, "compressed": compressed, "solved_ok": solved_ok,
           "competence": round(competence, 3), "novelty": round(novelty, 3), "round_evals": round_evals,
           "solver_prim_uses": solver_prim_uses, "frontier": dict(state["frontier"]), "details": details}
    state["history"].append({k: rec[k] for k in ("round", "tier_after", "competence", "novelty", "admitted")})
    return rec


# ===========================================================================
# X4.1 — EXTERNAL PROBLEM STREAM (owner 2026-07-23; docs/ATANOR_X4_external_problems_design.md)
# The decisive self-acceleration experiment: replace the self-composed target stream with an EXTERNAL,
# reach-expanding one and measure whether invented abstractions COMPOUND (open previously-unreachable
# problems) — the finite-ceiling test. All flags read AT CALL TIME, default OFF, so the baseline and the
# committed tests are byte-identical, and X1/X2/X3 compose independently.
# ===========================================================================
def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() not in ("", "0", "false", "no", "off")


def _external_on() -> bool:
    """ATANOR_EXTERNAL_PROBLEMS — draw the curriculum's targets from the external corpus (X4.1)."""
    return _flag("ATANOR_EXTERNAL_PROBLEMS")


def _ext_drive_on() -> bool:
    """ATANOR_COMPRESSION_DRIVE (X1) — rank the external pool by learning progress (compression
    progress of a short reconnaissance solution), not corpus order."""
    return _flag("ATANOR_COMPRESSION_DRIVE")


def _ext_qd_on() -> bool:
    """ATANOR_QD_ARCHIVE (X3) — maintain a MAP-Elites divergent archive of solved external programs and
    feed its diverse stepping stones to the miner."""
    return _flag("ATANOR_QD_ARCHIVE")


# ===========================================================================
# X4.2 — AUTONOMOUS STEPPING-STONE CLIMB (owner 2026-07-23)
# X4.1 proved external abstractions COMPOUND when a stepping stone is HANDED IN (8 cold-unreachable
# tasks opened), but AUTONOMOUS compounding was ~0 for two diagnosed reasons: (1) the compounding
# chain's FIRST RUNG is itself cold-unreachable so the loop never reaches the rung compounding fires
# from, and (2) the accumulated library DILUTES easy-task search (the frozen/empty library out-solved
# the grown live one). X4.2 makes the loop CLIMB the chain it traverses when handed the rung:
#   (i)   dependency-aware curriculum: attempt+master a task's rungs BEFORE the task (tier/dep-ordered,
#         X1 learning-progress preferring the learnable rung within a tier);
#   (ii)  singleton promotion: a mastered rung's program becomes a SOLVER PRIMITIVE (variabilise its
#         primary input into a hole) so the next task builds ON it in one step — the loop-closure the
#         mine() path cannot provide (mining needs a PAIR of blocks; a single rung would never promote);
#   (iii) scoped solver inputs: feed a small, relevant working set (bounded promoted primitives + a
#         parsimony library floor) instead of the whole accumulated library, so live is never diluted
#         below frozen on the easy tasks.
# Flag-gated OFF => byte-identical to the X4.1 external loop. Composable with X1/X2/X3.
# ===========================================================================
def _stepping_on() -> bool:
    """ATANOR_STEPPING_STONE (X4.2) — turn on the three autonomous-climb levers above."""
    return _flag("ATANOR_STEPPING_STONE")


# The family's PRIMARY input variable (the operand a rung transforms). Variabilising THIS leaf turns a
# single mastered rung into a reusable, parameterised solver primitive (arity 1) with no second block.
_PRIMARY_VAR = {"num": "a", "text": "s", "seq": "xs"}
_STEP_PRIM_CAP = 8     # max promoted primitives fed to the solver per family (primitive-side dilution cap)
_STEP_LIB_FLOOR = 4    # parsimony floor of smallest library blocks fed alongside (library-side dilution cap)
# A stepping stone only compounds once it is actually MASTERED, and the first rungs sit at the edge of the
# raw grammar's reach (e.g. map(x*x,xs) needs a wide search). So INVEST more search budget in a rung in
# proportion to its downstream LEVERAGE (how many tasks depend on it): the curriculum spends compute where
# it unlocks the most. This is resource allocation, not an answer — the rung is still rediscovered from I/O.
_MASTERY_GEN_BOOST = 1.5   # per-dependent generations multiplier increment for a rung
_MASTERY_DEP_BOOST = 2.0   # flat generations multiplier for a compounding DEPENDENT (the payoff wrapper)
_MASTERY_GEN_CAP = 220     # hard cap on a boosted task's generations (bounds waste on hard/unreachable rungs)
_MASTERY_POP_BOOST = 1.0   # population multiplier for a chain task (1.0 = gens-only boost, cheaper)
# A rung that keeps failing is (honestly) beyond the grammar's reach — e.g. filter-even needs an even-test
# the primitive set cannot cheaply express (an X4.3 primitive-TYPE gap, not a curriculum gap). After this
# many failed attempts, STOP flogging it: drop its priority + budget boost so the freed compute flows to
# the rungs that ARE masterable and to the dependents they unlock. Bounds wasted search; no false progress.
_RUNG_ATTEMPT_CAP = 2


def _variabilize(tree: Any, varname: str) -> tuple:
    """Turn a mastered rung's solved tree into a parameterised template by replacing every
    ('var', varname) leaf with a single shared hole ('hole', 0). All occurrences of the primary input map
    to the SAME hole (a genuine reused parameter), so the primitive applies the rung's transform to ANY
    sub-expression the solver plugs in. Returns (template, arity) with arity in {0, 1}."""
    found = [False]

    def go(t: Any) -> Any:
        if not isinstance(t, tuple) or not t:
            return t
        if t[0] == "var" and len(t) > 1 and t[1] == varname:
            found[0] = True
            return ("hole", 0)
        return tuple([t[0]] + [go(c) if isinstance(c, tuple) else c for c in t[1:]])

    return go(tree), (1 if found[0] else 0)


def _promote_primitive(state: dict[str, Any], family: str, tree: Any) -> bool:
    """X4.2 (ii) — promote a mastered rung's program into the SOLVER's primitive vocabulary. Variabilise
    the primary input into a hole, gate for NON-DEGENERACY (`_expands_reachable`: the output must depend
    on the hole AND reach a non-atomic behaviour) and NON-DUPLICATION, then store it in
    state['promoted'][family]. This is what lets a mastered rung open the compounding task autonomously —
    the next round's solver can instantiate it in one step via `_grow_primitive`. Returns whether a new
    primitive was promoted."""
    if _size(tree) > _MAX_KEEP_SIZE:
        return False
    tmpl, arity = _variabilize(tree, _PRIMARY_VAR[family])
    if arity < 1 or not _expands_reachable(tmpl, arity, family):
        return False
    src = to_source(tmpl)
    promoted = state.setdefault("promoted", {f: [] for f in _FAMILIES}).setdefault(family, [])
    if any(p["source"] == src for p in promoted):
        return False
    promoted.append({"template": tmpl, "arity": arity, "source": src, "uses": 0,
                     "born": state.get("round", 0)})
    return True


def _stepping_primitives(state: dict[str, Any], family: str) -> tuple:
    """X4.2 (ii+iii) the SCOPED solver primitive set: promoted rung primitives (pre-gated at promotion,
    ordered most-used-first) UNION the mined abstractions (`_solver_primitives`, already gated), deduped
    by source and BOUNDED to `_STEP_PRIM_CAP`. Bounding is the primitive-side dilution fix — an unbounded
    vocabulary makes the generator waste probability mass on irrelevant templates."""
    out, seen = [], set()
    for p in sorted(state.get("promoted", {}).get(family, ()),
                    key=lambda d: (-d.get("uses", 0), d.get("born", 0))):
        if p["source"] in seen:
            continue
        seen.add(p["source"])
        out.append({"template": p["template"], "arity": p["arity"]})
        if len(out) >= _STEP_PRIM_CAP:
            return tuple(out)
    for ab in _solver_primitives(state, family):
        key = to_source(ab["template"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ab)
        if len(out) >= _STEP_PRIM_CAP:
            break
    return tuple(out)


def _bump_primitive_uses(state: dict[str, Any], family: str, tree: Any) -> None:
    """Credit each promoted primitive a solution actually instantiated (the utility signal for the bounded
    most-used-first ordering)."""
    for p in state.get("promoted", {}).get(family, ()):
        if _uses_primitive(tree, ({"template": p["template"], "arity": p["arity"]},)):
            p["uses"] = p.get("uses", 0) + 1


def _scoped_library(state: dict[str, Any], family: str) -> tuple:
    """X4.2 (iii) library-side dilution fix — feed the solver only the `_STEP_LIB_FLOOR` smallest
    non-trivial library blocks (a parsimony floor) instead of the whole accumulated library, which was
    measured to slow easy-task search (frozen/empty out-solved the grown live one). The rung stepping
    stones travel through the PROMOTED PRIMITIVE channel, not the raw library, so a small floor loses no
    compounding while removing the dilution."""
    lib = state["libraries"][family]
    if len(lib) <= _STEP_LIB_FLOOR:
        return tuple(lib)
    return tuple(sorted(lib, key=_size)[:_STEP_LIB_FLOOR])


def _subtree_eq_any(tree: Any, blocks: list, min_size: int = 3) -> str | None:
    """PROVENANCE: does the solution literally REUSE a learned library block (a non-trivial solved
    sub-program appears as a subtree)? Returns the reused block's source, else None. This is the
    library-reuse channel of compounding (distinct from the invented-primitive channel)."""
    bset = {}
    for b in blocks:
        if isinstance(b, tuple) and _size(b) >= min_size:
            bset[b] = to_source(b)
    if not bset:
        return None
    for st in _subtrees(tree):
        if st in bset:
            return bset[st]
    return None


def _ext_lp_score(task: Any, fam_vars: list, lib: tuple, prims: tuple, templates: tuple,
                  rng: random.Random) -> float:
    """X1 learning-progress score for an unsolved external task: run a cheap reconnaissance search,
    then score its best partial solution by COMPRESSION PROGRESS against the current library — the
    learnable-but-not-yet-learned frontier (already-cheap solutions score ~0; noise scores ~0; the
    mid-frontier peaks). Faithful to compression_progress; bounded recon keeps it affordable."""
    from packages.evolution import external_corpus as _ec
    from packages.evolution import compression_progress as _cp
    train = _ec.sample_io(task, 10, random.Random(rng.randint(1, 10_000)))
    recon = evolve(train, fam_vars, library=lib, primitives=prims, pop=40, generations=32,
                   rng_seed=rng.randint(1, 10_000))
    tree = recon.get("tree")
    if tree is None:
        return 0.0
    try:
        return _cp.compression_progress(tree, list(lib), templates)
    except Exception:
        return 0.0


def external_round(state: dict[str, Any], rng: random.Random, *, problems: int = 6,
                   close_loop: bool = True, invent: bool = True, freeze_lib: bool = False,
                   pop: int = 80, base_budget: int = 90, corpus: list | None = None) -> dict[str, Any]:
    """One curriculum round whose TARGETS are REAL external functions (external_corpus), verified by I/O
    examples — the X4.1 experiment. Same admit / mine / library machinery as autonomous_round; the only
    change is the target stream. Tracks per-task solve round + PROVENANCE (did the solution reuse a
    learned primitive / library block) so the harness can measure COMPOUNDING against a frozen archive.
    `freeze_lib`/`invent`/`close_loop` are the ablation knobs (frozen archive = freeze_lib+not invent)."""
    from packages.evolution import external_corpus as _ec
    from packages.evolution import qd_archive as _qd
    corpus = corpus if corpus is not None else _ec.TASKS

    # X4.1 state (lazily initialised so new_state()/autonomous_round stay untouched).
    ext_solved: dict = state.setdefault("ext_solved", {})      # task name -> round first solved
    prov: dict = state.setdefault("ext_prov", {})              # task name -> provenance record
    state.setdefault("niches", {f: {} for f in _FAMILIES})     # X3 archive per family
    state.setdefault("ext_history", [])

    state["round"] += 1
    tier = state["tier"]
    drive, use_qd = _ext_drive_on(), _ext_qd_on()
    stepping = _stepping_on() and close_loop and invent      # X4.2 climb (no-op under frozen/open-loop)
    dep_count: dict = {}
    rung_names: set = set()
    ext_attempts: dict = state.setdefault("ext_attempts", {}) if stepping else {}
    if stepping:
        state.setdefault("promoted", {f: [] for f in _FAMILIES})
        for t in corpus:                                     # downstream leverage of each task (its rungs)
            for d in (getattr(t, "deps", ()) or ()):
                dep_count[d] = dep_count.get(d, 0) + 1
        rung_names = set(dep_count)                          # tasks something depends on = the rungs

    def _active_rung(name: str) -> bool:
        """A rung still worth prioritising/boosting: it is a rung and hasn't exhausted its attempt budget
        (a persistently-failing rung is deprioritised so compute flows to reachable stepping stones)."""
        return name in rung_names and ext_attempts.get(name, 0) < _RUNG_ATTEMPT_CAP

    def _prio(t: Any) -> int:
        """Selection priority band (lower = attempted first): (0) an active RUNG — master the stepping
        stone ASAP; (1) a READY DEPENDENT whose rungs are all mastered — strike the compounding payoff while
        its promoted primitive is fresh (otherwise the tier-2 dependent sinks below every tier-0/1 task in
        the (tier,name) order and is never selected in the bounded window); (2) everything else."""
        if _active_rung(t.name):
            return 0
        deps = getattr(t, "deps", ()) or ()
        if deps and all(d in ext_solved for d in deps):
            return 1
        return 2

    max_tier = max(t.tier for t in corpus)

    # Eligible = unsolved tasks at or below the difficulty ceiling; auto-unlock the next tier when the
    # current ceiling is exhausted so the curriculum always makes progress (mirrors the self-composed
    # controller's tier climb). X4.2: also GATE on stepping-stone dependencies — a task is not eligible
    # until every rung it builds on is mastered, so first-rung sub-abstractions are attempted BEFORE the
    # compounding tasks that need them. Never stalls: if the dep-gate empties the pool while tasks remain,
    # fall back to the tier-only pool (a genuinely unmasterable rung cannot freeze the whole curriculum).
    def _deps_ok(t: Any) -> bool:
        return all(d in ext_solved for d in (getattr(t, "deps", ()) or ()))

    def eligible_at(c: int) -> list:
        base = [t for t in corpus if t.tier <= c and t.name not in ext_solved]
        if stepping:
            gated = [t for t in base if _deps_ok(t)]
            return gated if gated else base
        return base

    if stepping:
        # X4.2: DEPENDENCY replaces TIER as the pacing mechanism — open every tier at once so the tier-1/2
        # RUNGS are eligible (and rung-prioritised) from round 1 instead of waiting for a slow tier climb;
        # the dependency gate + rung-priority ordering already sequence the climb correctly.
        ceiling = max_tier
        elig = eligible_at(ceiling)
    else:
        ceiling = min(tier, max_tier)
        elig = eligible_at(ceiling)
        while not elig and ceiling < max_tier:
            ceiling += 1
            state["tier"] = tier = ceiling
            elig = eligible_at(ceiling)

    attempts, solved_ok, admitted, compressed, details = 0, 0, 0, 0, []
    solver_prim_uses, round_evals = 0, 0
    compounded_this_round = []

    # --- target selection (X1 ranks by learning progress; else stable curriculum order) ---
    # X4.2: under the stepping-stone climb, rank RUNGS FIRST (a stepping stone only compounds once it is
    # mastered, so master the high-leverage ones ASAP), then by X1 learning-progress. The dependency GATE
    # already keeps a not-yet-reachable dependent out of the pool, so LP among the gated set is safe AND
    # useful: a dependent's LP SPIKES the moment its rung's primitive is promoted (recon now finds a
    # partial solution) — so a freshly-unlocked compounding task surfaces right after its rung is mastered.
    if elig:
        if drive:
            fam_prim = {}
            scored = []
            # X4.2: the recon window is bounded to 16 tasks; order it by PRIORITY BAND before truncating so
            # active rungs AND ready dependents are actually scored — otherwise `elig[:16]` (corpus/tier
            # order) is all num+text tier-0/1 and the seq rungs + tier-2 dependents never enter the window.
            recon_pool = (sorted(elig, key=lambda t: (_prio(t), t.tier, t.name)) if stepping else elig)
            for t in recon_pool[:16]:                           # bound the recon window
                lib = (_scoped_library(state, t.family) if stepping
                       else tuple(state["libraries"][t.family]))
                prims = fam_prim.setdefault(
                    t.family, (_stepping_primitives(state, t.family) if stepping
                               else (_solver_primitives(state, t.family) if (close_loop and invent) else ())))
                templates = tuple(a.get("template") for a in state["abstractions"].get(t.family, ()))
                s = _ext_lp_score(t, _FAMILIES[t.family]["vars_"], lib, prims, templates, rng)
                scored.append((s, t))
            key = ((lambda x: (_prio(x[1]), -x[0], x[1].tier, x[1].name)) if stepping
                   else (lambda x: (-x[0], x[1].tier, x[1].name)))
            scored.sort(key=key)
            selected = [t for _s, t in scored[:problems]]
        else:
            selected = sorted(elig, key=lambda t: (t.tier, t.name))[:problems]
    else:
        selected = []

    for task in selected:
        fam = task.family
        lib = state["libraries"][fam]
        # X4.2: feed a SCOPED working set (bounded promoted primitives + a small parsimony library floor);
        # X4.1/baseline: the whole accumulated library + mined primitives.
        if stepping:
            solver_prims = _stepping_primitives(state, fam)
            solve_lib = _scoped_library(state, fam)
        else:
            solver_prims = _solver_primitives(state, fam) if (close_loop and invent) else ()
            solve_lib = tuple(lib)
        train = _ec.sample_io(task, 14, rng)
        holdout = _ec.sample_io(task, 10, rng)
        budget = min(base_budget + 30 * task.tier, 300)
        solve_pop = pop
        active_rung = stepping and _active_rung(task.name)
        lev = dep_count.get(task.name, 0) if active_rung else 0   # rung leverage (only while still active)
        is_dependent = bool(stepping and (getattr(task, "deps", ()) or ()))  # a compounding payoff task
        if lev or is_dependent:
            # invest search where it compounds: RUNGS in proportion to leverage; DEPENDENTS get a flat
            # boost (the reduce/len wrapper over a promoted primitive is a wider search than a tier-0 task).
            mult = (1 + _MASTERY_GEN_BOOST * lev) if lev else _MASTERY_DEP_BOOST
            budget = min(int(budget * mult), _MASTERY_GEN_CAP)
            solve_pop = int(pop * _MASTERY_POP_BOOST)
        if stepping:
            ext_attempts[task.name] = ext_attempts.get(task.name, 0) + 1   # count this attempt
        res = evolve(train, _FAMILIES[fam]["vars_"], library=solve_lib, primitives=solver_prims,
                     pop=solve_pop, generations=budget, rng_seed=rng.randint(1, 10_000))
        round_evals += res["evals"]
        acc = bool(res["solved"] and (fitness(res["tree"], holdout) >= 1.0 if res["tree"] else False))
        attempts += 1
        verdict = "reject"
        if acc:
            solved_ok += 1
            used_prim = _uses_primitive(res["tree"], solver_prims)
            reused_block = _subtree_eq_any(res["tree"], lib)
            solver_prim_uses += bool(used_prim)
            if not freeze_lib:
                verdict = _admit(state, fam, res["tree"])
                admitted += verdict == "new"
                compressed += verdict == "compressed"
                if use_qd and _size(res["tree"]) <= _MAX_KEEP_SIZE and not _is_trivial(res["tree"], fam):
                    _qd.insert(state["niches"].setdefault(fam, {}), res["tree"], signature(res["tree"], fam),
                               _size(res["tree"]), to_source(res["tree"]), cap=64)
                if stepping:
                    _bump_primitive_uses(state, fam, res["tree"])   # credit any promoted primitive used
                    _promote_primitive(state, fam, res["tree"])     # this mastered rung -> solver primitive
            first_time = task.name not in ext_solved
            if first_time:
                ext_solved[task.name] = state["round"]
                prov[task.name] = {"tier": task.tier, "family": fam, "round": state["round"],
                                   "motif": task.motif, "used_primitive": bool(used_prim),
                                   "primitive_source": (used_prim if isinstance(used_prim, str) else None),
                                   "reused_library_block": reused_block,
                                   "program": res["program"]}
                if used_prim or reused_block:
                    compounded_this_round.append(task.name)
        details.append({"task": task.name, "tier": task.tier, "family": fam, "motif": task.motif,
                        "accepted": acc, "verdict": verdict,
                        "used_primitive": bool(acc and _uses_primitive(res["tree"], solver_prims)),
                        "reused_block": bool(acc and _subtree_eq_any(res["tree"], lib)),
                        "program": res["program"] if acc else None})

    # --- invent primitives (X2 via ATANOR_EGRAPH_ABSTRACTION), unless ablated ---
    invented = 0
    if invent and not freeze_lib:
        egraph_on = _flag("ATANOR_EGRAPH_ABSTRACTION")
        for family in _FAMILIES:
            mine_lib = (_qd.elites(state["niches"].get(family, {}))
                        if (use_qd and state["niches"].get(family)) else state["libraries"][family])
            if egraph_on:
                found = _egraph.mine(mine_lib, top_k=6, min_gain=2, pool_tags=tuple(_VALUE_TAGS),
                                     size_hi=11, root_ok=lambda t: True, source_of=to_source)
            else:
                found = mine(mine_lib, top_k=6, min_gain=2)
            state["abstractions"][family] = [
                {"template": a["template"], "arity": a["arity"], "source": a["source"], "gain": a["gain"]}
                for a in found]
            invented += len(found)

    # --- controller: same competence/novelty tier logic as the self-composed loop ---
    competence = (solved_ok / attempts) if attempts else 0.0
    novelty = (admitted / attempts) if attempts else 0.0
    moved = "hold"
    if competence >= _UP and novelty < _SATURATED:
        state["tier"] = min(tier + 1, max_tier)
        moved = "up" if state["tier"] != tier else "hold"
    elif novelty >= _FAST:
        state["tier"] = min(tier + 1, max_tier)
        moved = "up" if state["tier"] != tier else "hold"
    elif competence < _DOWN and tier > 0:
        state["tier"] = tier - 1
        moved = "down"
    # if every eligible task is solved but harder tiers remain, unlock them next round
    if not eligible_at(min(state["tier"], max_tier)) and state["tier"] < max_tier:
        state["tier"] = min(state["tier"] + 1, max_tier)
        moved = "up"

    distinct = sum(len(s) for s in state["sigs"].values())
    sizes = [_size(t) for f in _FAMILIES for t in state["libraries"][f]]
    solved_by_tier = {}
    for name in ext_solved:
        tt = prov[name]["tier"]
        solved_by_tier[tt] = solved_by_tier.get(tt, 0) + 1
    state["frontier"] = {"distinct_solved": distinct,
                         "compressions": state["frontier"].get("compressions", 0) + compressed,
                         "avg_size": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                         "invented_primitives": invented,
                         "external_solved": len(ext_solved),
                         "external_solved_by_tier": solved_by_tier}
    promoted_total = sum(len(v) for v in state.get("promoted", {}).values()) if stepping else 0
    rec = {"round": state["round"], "tier_before": tier, "tier_after": state["tier"], "move": moved,
           "ceiling": ceiling, "attempts": attempts, "admitted": admitted, "compressed": compressed,
           "solved_ok": solved_ok, "competence": round(competence, 3), "novelty": round(novelty, 3),
           "round_evals": round_evals, "solver_prim_uses": solver_prim_uses,
           "external_solved_total": len(ext_solved), "compounded_this_round": compounded_this_round,
           "frontier": dict(state["frontier"]), "details": details,
           "drive": drive, "qd": use_qd, "stepping": stepping, "promoted_primitives": promoted_total,
           "external": True}
    state["ext_history"].append({k: rec[k] for k in
                                 ("round", "tier_after", "attempts", "solved_ok", "admitted",
                                  "external_solved_total")})
    return rec
