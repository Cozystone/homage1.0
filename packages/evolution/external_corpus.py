# -*- coding: utf-8 -*-
"""X4.1 — T1 EXTERNAL problem corpus (owner 2026-07-23; docs/ATANOR_X4_external_problems_design.md).

WHY THIS FILE EXISTS (the decisive X4 question)
-----------------------------------------------
X1-X3 measured that fixed-axiom SELF-COMPOSITION is a structural finite ceiling: the abstractions the
engine invents while composing its OWN library are LATERAL (alternative spellings of already-reachable
functions), so they cannot compound and ④ plateaus. X4 tests whether EXTERNAL, reach-expanding problems
break that ceiling — problems whose intended solution is a REAL, human-meaningful transformation that
was NOT composed from our seed axioms, so an abstraction invented while solving problem N might open a
previously-unreachable problem N+k (the compounding the design measures).

PROVENANCE — REAL, EXTERNAL, GRADUATED (sealed gate a)
------------------------------------------------------
Each task is a REAL list/string/arithmetic transformation from the DreamCoder / program-synthesis
canonical domain (reverse, take/drop, count-if, sum-of-evens, product, factorial, power, sum-to-n,
palindrome, rotate, second-largest, dedup, run-length ...). Every task is specified ONLY by its
REFERENCE FUNCTION in plain Python semantics (`ref`) — NOT by a tree composed from our grammar. The
verifier the engine sees is the set of I/O examples `sample_io` produces by running `ref` on sampled
inputs; the search never sees `ref`. This is exactly the external-verification discipline of an I/O
program-synthesis benchmark: the function is defined in ordinary Python, the engine must REDISCOVER a
grammar program that reproduces the I/O. It is external because the SEMANTICS come from outside the
grammar's fixed-axiom reach, not from self-composition of solved blocks.

Reference outputs are clamped to the open_domain interpreter's own bounds (`_INT_CLAMP`, `MAX_LEN`,
`get`/`slice` index semantics) so that a CORRECT grammar program can match the I/O EXACTLY — the tiers
grade genuine synthesis difficulty, not an artefact of value-range mismatch.

GRADUATION + COMPOUNDING FAMILIES
---------------------------------
`tier` 0..3 grades difficulty (0 = single non-seed primitive; 1 = a 2-primitive composition; 2 = a
3-4 node composition or a bounded-recursion form; 3 = requires a primitive KIND the grammar does not
have — sort/dedup/hash — the primitive-type ceiling probe). `motif` tags COMPOUNDING FAMILIES: sets of
tasks that share reusable structure, so solving an easy member can teach a block/abstraction a harder
member needs (e.g. `count-if`: filter_even -> count_even -> count_gt3 all share `len(filter(pred,xs))`).
The compounding metric asks whether learning the easy member CAUSALLY opens the harder one (vs a frozen
archive). `reach` is the a-priori reachability annotation ('direct' | 'compose' | 'none'); the actual
measurement is empirical.

SAFETY. Pure data: reference functions are ordinary Python run by THIS module to MANUFACTURE I/O
examples (never exec'd by the engine); the engine only ever interprets grammar trees over the
whitelisted open_domain kernel. No corpus is learned from; every I/O pair is a verified fact.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.evolution import open_domain as _od

# Mirror the interpreter's bounds so a correct program matches the reference EXACTLY.
_CLAMP = _od._INT_CLAMP
_MAXLEN = _od.MAX_LEN


def _ci(n: int) -> int:
    """Clamp an int to the interpreter's range (open_domain._clamp_int)."""
    return _CLAMP if n > _CLAMP else (-_CLAMP if n < -_CLAMP else n)


# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Task:
    name: str
    family: str                      # 'num' | 'text' | 'seq'  (open_domain families)
    tier: int                        # 0 (easy) .. 3 (primitive-type ceiling)
    ref: Callable[[dict], Any]       # REAL semantics in plain Python (never seen by the search)
    motif: str = ""                  # compounding-family tag ('' = standalone)
    reach: str = "direct"            # a-priori: 'direct' | 'compose' | 'none' (measurement is empirical)
    deps: tuple = ()                 # X4.2 STEPPING-STONE PREREQUISITES: names of the RUNG task(s) this
    #                                  task builds ON. This is CURRICULUM ORDERING METADATA ONLY — like
    #                                  `tier`/`reach`, it names which sub-abstraction to MASTER FIRST so
    #                                  the loop climbs the chain in dependency order. It is NEVER handed to
    #                                  the solver (the solver still rediscovers every program from I/O);
    #                                  the compounding it enables is measured empirically vs a frozen
    #                                  archive. `deps=()` = a first-rung / standalone task.
    note: str = ""
    sampler: Callable[[int, Any], list] | None = None   # X4.3 optional custom I/O maker: some tasks (grids)
    #                                  need inputs the family's default _sample_env does not produce (a
    #                                  planted H x W grid, not a short random sequence). When set, sample_io
    #                                  uses it INSTEAD of _sample_env; it still manufactures verified I/O by
    #                                  running the real reference — the solver never sees `ref` or `sampler`.


# ---------------------------------------------------------------------------
# Reference helpers (plain Python; clamp/cap to interpreter semantics)
# ---------------------------------------------------------------------------
def _prod(xs: tuple) -> int:
    p = 1
    for x in xs:
        p = _ci(p * x)
    return p


def _fact(a: int) -> int:
    p = 1
    for i in range(1, a + 1):
        p = _ci(p * i)
    return p


def _pow(a: int, b: int) -> int:
    r = 1
    for _ in range(b):
        r = _ci(r * a)
    return r


def _get(seq, i: int):
    """Mirror interpreter `get`: seq[i % len]; empty -> 0."""
    if not seq:
        return 0
    return seq[i % len(seq)]


def _slice(seq, i: int, j: int):
    """Mirror interpreter `slice`: clamp i,j to [-n,n]; empty -> empty."""
    n = len(seq)
    if n == 0:
        return seq
    i = max(-n, min(n, i))
    j = max(-n, min(n, j))
    return seq[i:j]


# ---------------------------------------------------------------------------
# X4.3 grid connected-component references (the ARC connection). Computed with the SAME bounded routines
# the interpreter uses (_od._grid_adjacency / _reach_from / _component_labels) so a correct meta-basis
# program reproduces the I/O EXACTLY. Grid is flat row-major in `xs`, width in `n`. Defined BEFORE TASKS
# because the grid Task rows bind these as `ref`/`sampler` at list-construction time.
# ---------------------------------------------------------------------------
def _grid_obj_size0(e: dict) -> int:
    return len(_od._reach_from(_od._grid_adjacency(e["xs"], e["n"]), 0))


def _grid_obj_size0_ge3(e: dict) -> int:
    return 1 if _grid_obj_size0(e) >= 3 else 0


def _grid_num_objects(e: dict) -> int:
    lab = _od._component_labels(_od._grid_adjacency(e["xs"], e["n"]))
    return sum(1 for i, m in enumerate(lab) if m == i)


def _grid_sampler(ref: Callable[[dict], Any], plant_corner: bool) -> Callable[[int, Any], list]:
    """Task-specific I/O maker: H x W grids (H,W in 2..4), cells 0/1 with an occasional colour 2 so
    components are colour-separated. `plant_corner` fills cell 0 so 'the object at cell 0' is defined.
    Still manufactures VERIFIED I/O by running the real reference; the solver never sees ref/sampler."""
    def make(n: int, rng: random.Random) -> list:
        out: list = []
        seen: set = set()
        tries = 0
        while len(out) < n and tries < n * 20:
            tries += 1
            w = rng.randint(2, 4)
            h = rng.randint(2, 4)
            cells = []
            for _ in range(w * h):
                rr = rng.random()
                cells.append(0 if rr < 0.42 else (1 if rr < 0.86 else 2))
            if plant_corner:
                cells[0] = 1
            g = tuple(cells)
            if (g, w) in seen:
                continue
            seen.add((g, w))
            env = {"xs": g, "n": w}
            out.append((env, ref(env)))
        return out
    return make


# ---------------------------------------------------------------------------
# THE CORPUS — graduated real functions across num / text / seq (+ X4.3 grid segmentation tasks).
# ---------------------------------------------------------------------------
TASKS: list[Task] = [
    # ===================== num (a, b in 0..9) =====================
    Task("num_add_one",   "num", 0, lambda e: _ci(e["a"] + 1), "affine", note="a+1"),
    Task("num_double",    "num", 0, lambda e: _ci(e["a"] * 2), "affine", note="2a"),
    Task("num_mul",       "num", 0, lambda e: _ci(e["a"] * e["b"]), note="a*b"),
    Task("num_mod3",      "num", 0, lambda e: e["a"] % 3, note="a mod 3"),
    Task("num_min",       "num", 1, lambda e: min(e["a"], e["b"]), "extremum", note="min(a,b) (mirror of max seed)"),
    Task("num_abs_diff",  "num", 1, lambda e: abs(e["a"] - e["b"]), "extremum", note="|a-b|"),
    Task("num_avg_floor", "num", 1, lambda e: (e["a"] + e["b"]) // 2, note="(a+b)//2"),
    Task("num_sq_plus_b", "num", 1, lambda e: _ci(e["a"] * e["a"] + e["b"]), note="a*a+b (reuses square)"),
    Task("num_sum_to_n",  "num", 2, lambda e: _ci(e["a"] * (e["a"] + 1) // 2), "fold-range", reach="compose",
         note="0+1+..+a"),
    Task("num_sum_sq_ton","num", 2, lambda e: _ci(sum(i * i for i in range(e["a"] + 1))), "fold-range",
         reach="compose", note="sum of i^2 for i<=a"),
    Task("num_factorial", "num", 2, lambda e: _fact(e["a"]), "fold-range", reach="compose", note="a!"),
    Task("num_power",     "num", 2, lambda e: _pow(e["a"], e["b"]), "iterate", reach="compose", note="a^b"),
    Task("num_gcd",       "num", 3, lambda e: _gcd(e["a"], e["b"]), "euclid", reach="none",
         note="gcd — unbounded conditional recursion, likely out of reach"),

    # ===================== text (s in a..p len 0..6, k in 0..5) =====================
    Task("txt_upper",     "text", 0, lambda e: e["s"].upper(), "case", note="uppercase"),
    Task("txt_lower",     "text", 0, lambda e: e["s"].lower(), "case", note="lowercase"),
    Task("txt_first",     "text", 0, lambda e: _get(e["s"], 0), "index", note="s[0]"),
    Task("txt_repeat_k",  "text", 0, lambda e: (e["s"] * e["k"])[:_MAXLEN], note="s repeated k times"),
    Task("txt_take_k",    "text", 0, lambda e: _slice(e["s"], 0, e["k"]), "slice", note="s[:k]"),
    Task("txt_drop_k",    "text", 1, lambda e: _slice(e["s"], e["k"], len(e["s"])), "slice", note="s[k:]"),
    Task("txt_last",      "text", 1, lambda e: _get(e["s"], len(e["s"]) - 1), "index", reach="compose",
         note="s[-1]"),
    Task("txt_palindrome","text", 1, lambda e: (e["s"] + e["s"][::-1])[:_MAXLEN], "mirror", reach="compose",
         note="s + reverse(s)"),
    Task("txt_rev_twice", "text", 1, lambda e: (e["s"][::-1] + e["s"][::-1])[:_MAXLEN], "mirror",
         reach="compose", note="rev(s)+rev(s)"),
    Task("txt_take_last_k","text", 2, lambda e: _slice(e["s"], len(e["s"]) - e["k"], len(e["s"])), "slice",
         reach="compose", note="s[-k:]"),
    Task("txt_rotate1",   "text", 2, lambda e: (_slice(e["s"], 1, len(e["s"])) + _slice(e["s"], 0, 1))[:_MAXLEN],
         "rotate", reach="compose", note="rotate left by 1"),
    Task("txt_dedup_adj", "text", 3, lambda e: _dedup_adj(e["s"]), "dedup", reach="none",
         note="collapse adjacent dups — needs statefully-conditioned build"),

    # ===================== seq (xs of 0..7 len 0..6, n in 0..5) =====================
    Task("seq_inc_each",  "seq", 0, lambda e: tuple(_ci(x + 1) for x in e["xs"]), "map", note="map (+1)"),
    Task("seq_double_each","seq", 0, lambda e: tuple(_ci(x * 2) for x in e["xs"]), "map", note="map (*2)"),
    Task("seq_reverse",   "seq", 0, lambda e: e["xs"][::-1], note="reverse"),
    Task("seq_take_n",    "seq", 0, lambda e: _slice(e["xs"], 0, e["n"]), "slice", note="xs[:n]"),
    Task("seq_product",   "seq", 1, lambda e: _prod(e["xs"]), "fold", note="product of xs"),
    Task("seq_square_each","seq", 1, lambda e: tuple(_ci(x * x) for x in e["xs"]), "map", note="map (x*x)"),
    Task("seq_drop_n",    "seq", 1, lambda e: _slice(e["xs"], e["n"], len(e["xs"])), "slice", note="xs[n:]"),
    Task("seq_filter_even","seq", 1, lambda e: tuple(x for x in e["xs"] if x % 2 == 0), "count-if",
         note="keep evens"),
    Task("seq_filter_gt3","seq", 1, lambda e: tuple(x for x in e["xs"] if x > 3), "count-if",
         note="keep > 3"),
    Task("seq_count_even","seq", 2, lambda e: len([x for x in e["xs"] if x % 2 == 0]), "count-if",
         reach="compose", deps=("seq_filter_even",), note="len(filter even) — count-if motif"),
    Task("seq_count_gt3", "seq", 2, lambda e: len([x for x in e["xs"] if x > 3]), "count-if",
         reach="compose", deps=("seq_filter_gt3",), note="len(filter >3) — count-if motif"),
    Task("seq_sum_evens", "seq", 2, lambda e: _ci(sum(x for x in e["xs"] if x % 2 == 0)), "sum-filter",
         reach="compose", deps=("seq_filter_even",), note="reduce(+,0,filter even)"),
    Task("seq_sum_gt3",   "seq", 2, lambda e: _ci(sum(x for x in e["xs"] if x > 3)), "sum-filter",
         reach="compose", deps=("seq_filter_gt3",), note="reduce(+,0,filter >3)"),
    Task("seq_sum_squares","seq", 2, lambda e: _ci(sum(x * x for x in e["xs"])), "sum-map", reach="compose",
         deps=("seq_square_each",), note="reduce(+,0,map x*x)"),
    Task("seq_max",       "seq", 2, lambda e: (max(e["xs"]) if e["xs"] else 0), "extremum", reach="compose",
         note="max element"),
    Task("seq_min",       "seq", 2, lambda e: (min(e["xs"]) if e["xs"] else 0), "extremum", reach="compose",
         note="min element"),
    Task("seq_max_minus_min","seq", 2, lambda e: (max(e["xs"]) - min(e["xs"]) if e["xs"] else 0), "extremum",
         reach="compose", deps=("seq_max", "seq_min"), note="range = max - min (needs BOTH extrema)"),
    Task("seq_second_max","seq", 3, lambda e: _second_max(e["xs"]), "sort", reach="none",
         note="2nd largest — needs sort/selection, no such primitive KIND"),
    Task("seq_dedup_count","seq", 3, lambda e: len(set(e["xs"])), "dedup", reach="none",
         note="count distinct — needs a set/hash primitive KIND"),
    Task("seq_median",    "seq", 3, lambda e: _median(e["xs"]), "sort", reach="none",
         note="median — needs sort"),
    Task("seq_sort",      "seq", 3, lambda e: tuple(sorted(e["xs"])), "sort", reach="none",
         note="ascending sort — needs recursion + comparison (no sort primitive KIND)"),

    # =============== grid connected-component (X4.3 — the ARC connection, family 'seq': xs=flat grid,
    # n=width). Tier 3: needs a transitive-closure KIND the base grammar entirely lacks. ============
    Task("grid_obj_size0", "seq", 3, _grid_obj_size0, "segment", reach="none",
         sampler=_grid_sampler(_grid_obj_size0, plant_corner=True),
         note="size of the object touching cell 0 — len(reach(edges(g,w),0))"),
    Task("grid_obj_size0_ge3", "seq", 3, _grid_obj_size0_ge3, "segment", reach="none",
         sampler=_grid_sampler(_grid_obj_size0_ge3, plant_corner=True),
         note="DEPENDENT (harness-managed): is the cell-0 object big (>=3)? — builds on promoted obj_size0"),
    Task("grid_num_objects", "seq", 3, _grid_num_objects, "segment", reach="none",
         sampler=_grid_sampler(_grid_num_objects, plant_corner=False),
         note="number of objects — len(filter(_x==_i, closure(edges(g,w))))"),
]


# --- reference helpers for the harder tiers ---
def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _dedup_adj(s: str) -> str:
    out = []
    for ch in s:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)[:_MAXLEN]


def _second_max(xs: tuple) -> int:
    if len(xs) < 2:
        return 0
    a = sorted(xs, reverse=True)
    return a[1]


def _median(xs: tuple) -> int:
    if not xs:
        return 0
    a = sorted(xs)
    return a[len(a) // 2]


# ---------------------------------------------------------------------------
# I/O manufacture (the external verifier the engine sees) — mirrors open_domain._sample_env
# so inputs are in-distribution for the interpreter, and dedups example inputs.
# ---------------------------------------------------------------------------
def sample_io(task: Task, n: int, rng: random.Random) -> list[tuple[dict, Any]]:
    """Manufacture n distinct input->output examples by running the REAL reference function. This is
    the ONLY thing the engine sees for the task — the external verification set. `ref` itself is never
    exposed to the search."""
    if task.sampler is not None:                              # X4.3: task-specific input distribution
        return task.sampler(n, rng)
    out: list[tuple[dict, Any]] = []
    seen: set = set()
    tries = 0
    while len(out) < n and tries < n * 12:
        tries += 1
        env = _od._sample_env(task.family, rng)
        key = repr(sorted((k, repr(v)) for k, v in env.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append((env, task.ref(env)))
    return out


def by_tier(tier: int) -> list[Task]:
    return [t for t in TASKS if t.tier == tier]


def by_family(family: str) -> list[Task]:
    return [t for t in TASKS if t.family == family]


def motif_families() -> dict[str, list[Task]]:
    """Group tasks by compounding-motif tag (drop standalone '' tag)."""
    out: dict[str, list[Task]] = {}
    for t in TASKS:
        if t.motif:
            out.setdefault(t.motif, []).append(t)
    return out


def stepping_stones() -> dict[str, tuple]:
    """X4.2 curriculum dependency graph: {dependent_task_name -> (rung_task_name, ...)}. The rung is the
    sub-abstraction the dependent must MASTER first for compounding to fire (e.g. seq_count_even builds on
    seq_filter_even). Ordering metadata only — the solver never sees it."""
    return {t.name: t.deps for t in TASKS if t.deps}


def rungs() -> set:
    """The set of task names that are a stepping-stone rung for some dependent (the first rungs to master)."""
    out: set = set()
    for deps in stepping_stones().values():
        out.update(deps)
    return out


def provenance() -> dict[str, Any]:
    """A machine-readable summary of the corpus for the sealed-gate report."""
    tiers = {i: len(by_tier(i)) for i in range(4)}
    fams = {f: len(by_family(f)) for f in ("num", "text", "seq")}
    return {
        "size": len(TASKS),
        "tiers": tiers,
        "families": fams,
        "motifs": {m: [t.name for t in ts] for m, ts in motif_families().items()},
        "stepping_stones": stepping_stones(),
        "rungs": sorted(rungs()),
        "external": True,
        "self_composed": False,
        "verifier": "io_examples",
        "reference_semantics": "plain_python_clamped_to_interpreter_bounds",
    }
