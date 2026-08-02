# -*- coding: utf-8 -*-
"""Algorithm schemas — domain-blind LAWS of algorithm shape, the first slab of the System-2 substrate.

A schema is to an algorithm what a mechanism.py micro-law is to a physical situation: the SCAFFOLD is
owned as structure (a table filled left-to-right, a queue drained by indegree, a per-row placement
tree), and only the smallest HOLES are enumerated — an initial-cell expression, a recurrence, a
constraint, a frontier discipline. Everything a schema emits is still a candidate BODY that must pass
the isolated verifier in code_author; a schema never certifies itself, and when no instantiation
passes the engine ABSTAINS. So this raises the ceiling (it reaches the hard rung: edit distance,
LCS, topological sort, n-queens counting, coin change, interval merge) WITHOUT any task-specific
memorized answer and WITHOUT weakening the no-fabrication floor.

Each Schema = {id, cue (applicability from docstring verbs + signature arity), fill (a generator that
yields fully-formed candidate bodies by filling the holes from small grammars)}. Hole grammars are
tiny (a handful each) and every schema caps its own instantiation count, so the whole search stays
well under the runtime budget. Canonical hole choices are yielded FIRST, so the correct law is the
first thing certified and a coincidental wrong instantiation never ships ahead of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator


def _has(intent: str, words: tuple[str, ...]) -> bool:
    il = intent.lower()
    return any(w in il for w in words)


# --------------------------------------------------------------------- DP-2D (two sequences)
# Scaffold: a (m+1) x (n+1) table over two sequences; fill row-major from three neighbours.
# Holes: INIT boundary cell, MATCH cell (a[i-1]==b[j-1]), MISMATCH cell. Reaches edit distance & LCS.

def _cue_dp2d(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("distance", "subsequence", "common", "edit", "align",
                                              "longest"))


def _fill_dp2d(params: list[str], intent: str) -> Iterator[str]:
    a, b = params
    inits = ["_i + _j", "0", "_i if _j == 0 else _j"]                       # boundary cell (i,j)
    matches = ["_dp[_i - 1][_j - 1]", "_dp[_i - 1][_j - 1] + 1"]           # when a[i-1]==b[j-1]
    mismatches = [
        "1 + min(_dp[_i - 1][_j], _dp[_i][_j - 1], _dp[_i - 1][_j - 1])",   # edit distance
        "max(_dp[_i - 1][_j], _dp[_i][_j - 1])",                            # LCS
        "min(_dp[_i - 1][_j], _dp[_i][_j - 1])",
        "1 + min(_dp[_i - 1][_j], _dp[_i][_j - 1])",
    ]
    for init in inits:
        for mt in matches:
            for mm in mismatches:
                recur = f"{mt} if {a}[_i - 1] == {b}[_j - 1] else {mm}"
                yield (
                    f"_m, _n = len({a}), len({b})\n"
                    f"_dp = [[{init} for _j in range(_n + 1)] for _i in range(_m + 1)]\n"
                    f"for _i in range(1, _m + 1):\n"
                    f"    for _j in range(1, _n + 1):\n"
                    f"        _dp[_i][_j] = {recur}\n"
                    f"return _dp[_m][_n]"
                )


# --------------------------------------------------------------------- TOPO (Kahn)
# Scaffold: indegree + adjacency from an edge list, drain a frontier. Holes: frontier init, pop
# discipline, whether to re-sort (a deterministic lexicographic topological order).

def _cue_topo(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("topolog", "edges", "nodes", "adjac"))


def _fill_topo(params: list[str], intent: str) -> Iterator[str]:
    n, edges = params
    readys = [f"sorted(_x for _x in range({n}) if _indeg[_x] == 0)",
              f"[_x for _x in range({n}) if _indeg[_x] == 0]"]
    pops = ["_ready.pop(0)", "_ready.pop()"]
    reorders = ["    _ready.sort()", "    pass"]
    for ready in readys:
        for pop in pops:
            for reorder in reorders:
                yield (
                    f"_indeg = [0] * {n}\n"
                    f"_adj = [[] for _ in range({n})]\n"
                    f"for _u, _v in {edges}:\n"
                    f"    _adj[_u].append(_v)\n"
                    f"    _indeg[_v] += 1\n"
                    f"_ready = {ready}\n"
                    f"_order = []\n"
                    f"while _ready:\n"
                    f"    _node = {pop}\n"
                    f"    _order.append(_node)\n"
                    f"    for _w in _adj[_node]:\n"
                    f"        _indeg[_w] -= 1\n"
                    f"        if _indeg[_w] == 0:\n"
                    f"            _ready.append(_w)\n"
                    f"{reorder}\n"
                    f"return _order"
                )


# --------------------------------------------------------------------- DP-1D (linear table over a sequence)
# Scaffold: dp[0..size] filled left-to-right, inner loop over a coin/step sequence. Holes: the base seed
# dp[0], the sentinel rest, the recurrence, the answer extraction. Reaches BOTH min-coin change (seed 0,
# rest size+1, min-recurrence) and ordered change-counting (seed 1, rest 0, additive recurrence) — two
# genuinely-distinct instantiations of the same linear-DP law, which is what lets L3 anti-unify a
# >= 2-exemplar DP-1D family and reinvent the scaffold from the corpus (v1 could reach only one).

def _cue_dp1d(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("fewest", "coins", "change", "denomination"))


def _fill_dp1d(params: list[str], intent: str) -> Iterator[str]:
    seq, size = params
    seeds = ["0", "1"]                                                    # dp[0] base case
    init_rests = [f"{size} + 1", "0"]                                    # dp[1..size] sentinel
    recurs = ["min(_dp[_k], _dp[_k - _c] + 1)", "_dp[_k] + _dp[_k - _c]"]
    answers = [f"_dp[{size}] if _dp[{size}] <= {size} else -1", f"_dp[{size}]"]
    for seed in seeds:
        for ir in init_rests:
            for rc in recurs:
                for ans in answers:
                    yield (
                        f"_dp = [{seed}] + [{ir}] * {size}\n"
                        f"for _k in range(1, {size} + 1):\n"
                        f"    for _c in {seq}:\n"
                        f"        if _c <= _k:\n"
                        f"            _dp[_k] = {rc}\n"
                        f"return {ans}"
                    )


# --------------------------------------------------------------------- BACKTRACK-count
# Scaffold: place one choice per row, count complete placements. Hole: the reject CONSTRAINT (which
# conflicts to enforce). Reaches n-queens counting.

def _cue_backtrack(params: list[str], intent: str) -> bool:
    return (len(params) == 1
            and _has(intent, ("queen", "solutions", "arrangements", "placements", "ways"))
            and _has(intent, ("count", "number", "distinct", "how many")))


def _fill_backtrack(params: list[str], intent: str) -> Iterator[str]:
    n = params[0]
    constraints = [
        "_col in _cols or (_row - _col) in _d1 or (_row + _col) in _d2",   # n-queens
        "_col in _cols or (_row - _col) in _d1",
        "_col in _cols or (_row + _col) in _d2",
        "_col in _cols",
    ]
    for con in constraints:
        yield (
            f"def _rec(_row, _cols, _d1, _d2):\n"
            f"    if _row == {n}:\n"
            f"        return 1\n"
            f"    _total = 0\n"
            f"    for _col in range({n}):\n"
            f"        if {con}:\n"
            f"            continue\n"
            f"        _total += _rec(_row + 1, _cols | {{_col}}, _d1 | {{_row - _col}}, "
            f"_d2 | {{_row + _col}})\n"
            f"    return _total\n"
            f"return _rec(0, set(), set(), set())"
        )


# --------------------------------------------------------------------- GREEDY-sort-loop
# Scaffold: sort, then fold left. Hole: the fold step (here the interval-merge fold). Reaches
# interval merge.

def _cue_greedy(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("merge", "interval", "overlap"))


def _fill_greedy(params: list[str], intent: str) -> Iterator[str]:
    seq = params[0]
    yield (
        f"_items = sorted({seq})\n"
        f"_out = []\n"
        f"for _it in _items:\n"
        f"    if _out and _it[0] <= _out[-1][1]:\n"
        f"        _out[-1] = (_out[-1][0], max(_out[-1][1], _it[1]))\n"
        f"    else:\n"
        f"        _out.append(_it)\n"
        f"return _out"
    )


# --------------------------------------------------------------------- GRAPH-traversal
# Scaffold: adjacency from edges, drain a frontier from node 0, accumulate the visited set. Holes:
# frontier discipline (queue=BFS | stack=DFS) and the answer read. Reachability / connectivity.

def _cue_graph(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("reachable", "connected", "traversal", "visit", "bfs",
                                              "dfs"))


def _fill_graph(params: list[str], intent: str) -> Iterator[str]:
    n, edges = params
    pops = ["_frontier.pop(0)", "_frontier.pop()"]
    answers = ["len(_seen)", "sorted(_seen)"]
    for pop in pops:
        for ans in answers:
            yield (
                f"_adj = [[] for _ in range({n})]\n"
                f"for _u, _v in {edges}:\n"
                f"    _adj[_u].append(_v)\n"
                f"    _adj[_v].append(_u)\n"
                f"_seen = {{0}}\n"
                f"_frontier = [0]\n"
                f"while _frontier:\n"
                f"    _node = {pop}\n"
                f"    for _w in _adj[_node]:\n"
                f"        if _w not in _seen:\n"
                f"            _seen.add(_w)\n"
                f"            _frontier.append(_w)\n"
                f"return {ans}"
            )


# --------------------------------------------------------------------- SCAN-RUN (run accumulation)
# Scaffold: walk a sequence, grow a run while the run-key is unchanged, emit on each break. Holes:
# run-key expr, per-run emit expr, final answer. Reaches run-length encode (and, generally, run
# lengths / longest run / case-folded runs).

def _cue_scanrun(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("run", "consecutive"))


def _fill_scanrun(params: list[str], intent: str) -> Iterator[str]:
    s = params[0]
    keys = ["_x", "_x.lower()"]                                   # run-key over the current element
    emits = ["(_start, _run)", "_run", "_start"]                 # what each finished run contributes
    answers = ["_out", "max(_out)"]                              # collect the runs, or reduce them
    for key in keys:
        for emit in emits:
            for ans in answers:
                yield (
                    f"_out = []\n_prev = None\n_start = None\n_run = 0\n"
                    f"for _x in {s}:\n"
                    f"    _k = {key}\n"
                    f"    if _run and _k == _prev:\n"
                    f"        _run += 1\n"
                    f"    else:\n"
                    f"        if _run:\n"
                    f"            _out.append({emit})\n"
                    f"        _prev = _k\n        _start = _x\n        _run = 1\n"
                    f"if _run:\n    _out.append({emit})\n"
                    f"return {ans}"
                )


# --------------------------------------------------------------------- GROUP-BY (key -> list fold)
# Scaffold: fold items into a dict keyed by KEY(item), then finalize. Hole: the key expression (from
# a small grammar). Reaches anagram grouping (key = sorted letters) and, generally, group-by-length,
# group-by-first-letter, ...

def _cue_groupby(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("group", "anagram", "bucket"))


def _fill_groupby(params: list[str], intent: str) -> Iterator[str]:
    w = params[0]
    keys = ["''.join(sorted(_it))", "len(_it)", "_it[0]", "_it[-1]"]
    finals = ["sorted(sorted(_g) for _g in _groups.values())",
              "[_groups[_k] for _k in sorted(_groups)]"]
    for key in keys:
        for final in finals:
            yield (
                f"_groups = {{}}\n"
                f"for _it in {w}:\n"
                f"    _groups.setdefault({key}, []).append(_it)\n"
                f"return {final}"
            )


# --------------------------------------------------------------------- STACK-SCAN (push/pop automaton)
# Scaffold: push openers, on a closer check it matches the top. Hole: the bracket-pair table (a small
# grammar of alphabets) and the accept condition. Reaches bracket balancing over any of those
# alphabets.

def _cue_stackscan(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("bracket", "balanced", "parenthes", "matched"))


def _fill_stackscan(params: list[str], intent: str) -> Iterator[str]:
    s = params[0]
    pair_tables = [
        "{')': '(', ']': '[', '}': '{'}",
        "{'>': '<'}",
        "{')': '('}",
        "{')': '(', ']': '[', '}': '{', '>': '<'}",
    ]
    accepts = ["not _stack", "len(_stack) == 0"]
    for pairs in pair_tables:
        for accept in accepts:
            yield (
                f"_pairs = {pairs}\n"
                f"_openers = set(_pairs.values())\n"
                f"_stack = []\n"
                f"for _c in {s}:\n"
                f"    if _c in _openers:\n"
                f"        _stack.append(_c)\n"
                f"    elif _c in _pairs:\n"
                f"        if not _stack or _stack.pop() != _pairs[_c]:\n"
                f"            return False\n"
                f"return {accept}"
            )


# --------------------------------------------------------------------- VALUE-MAP-SCAN (INDUCED table)
# The doctrine showcase: the scan LAW (lookahead — subtract a symbol whose value is less than its
# successor's, else add) is owned as structure; the per-symbol values are CONTENT, learned from the
# task's own visible examples by constraint-solving, never hardcoded. If the examples do not pin a
# consistent table, the schema emits nothing and the engine abstains. Reaches roman-to-int and any
# other subtractive numeral system.

def _cue_valuemap(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("numeral", "roman"))


def _induce_value_map(pairs: list[tuple[str, int]]) -> dict | None:
    """Seed each symbol's value from a pure-repeat example (value divisible by length); require every
    symbol present to be pinned this way and mutually consistent, else None (-> abstain). The
    combination rule itself is NOT induced — it is the scan law, verified against the composites."""
    v: dict = {}
    for s, val in pairs:
        if s and len(set(s)) == 1 and isinstance(val, int) and val % len(s) == 0:
            base = val // len(s)
            if base <= 0:
                return None
            if s[0] in v and v[s[0]] != base:
                return None
            v[s[0]] = base
    symbols: set = set()
    for s, _ in pairs:
        symbols |= set(s)
    if not symbols or not symbols <= set(v):
        return None
    return v


def _fill_valuemap(params: list[str], intent: str, examples: tuple) -> Iterator[str]:
    pairs = [(a[0], val) for a, val in examples
             if len(a) == 1 and isinstance(a[0], str) and isinstance(val, int)]
    if not pairs:
        return
    table = _induce_value_map(pairs)
    if table is None:
        return                                               # under-determined -> honest abstain
    s = params[0]
    literal = "{" + ", ".join(f"{c!r}: {val}" for c, val in sorted(table.items())) + "}"
    yield (
        f"_v = {literal}\n"
        f"_total = 0\n"
        f"for _i in range(len({s})):\n"
        f"    if _i + 1 < len({s}) and _v[{s}[_i]] < _v[{s}[_i + 1]]:\n"
        f"        _total -= _v[{s}[_i]]\n"
        f"    else:\n"
        f"        _total += _v[{s}[_i]]\n"
        f"return _total"
    )


# --------------------------------------------------------------------- DP-STRING (prefix membership DP)
# Scaffold: dp over prefixes of a string, extended by a dictionary-membership test on a substring.
# Hole: accumulate as boolean-any (segmentable?) or integer-count (# of segmentations). Reaches
# word-break and segmentation counting.

def _cue_dpstring(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("segment", "break into", "dictionary", "compose"))


def _fill_dpstring(params: list[str], intent: str) -> Iterator[str]:
    s, words = params
    yield (                                                       # any-mode: is it segmentable?
        f"_d = set({words})\n_dp = [False] * (len({s}) + 1)\n_dp[0] = True\n"
        f"for _i in range(1, len({s}) + 1):\n"
        f"    for _j in range(_i):\n"
        f"        if _dp[_j] and {s}[_j:_i] in _d:\n"
        f"            _dp[_i] = True\n            break\n"
        f"return _dp[len({s})]"
    )
    yield (                                                       # count-mode: # of segmentations
        f"_d = set({words})\n_dp = [0] * (len({s}) + 1)\n_dp[0] = 1\n"
        f"for _i in range(1, len({s}) + 1):\n"
        f"    for _j in range(_i):\n"
        f"        if {s}[_j:_i] in _d:\n"
        f"            _dp[_i] += _dp[_j]\n"
        f"return _dp[len({s})]"
    )


# --------------------------------------------------------------------- REACH-SET (subset reachability)
# Scaffold: accumulate the set of reachable sums by folding each item into the running reachable set.
# Hole: the answer read. Reaches subset-sum (membership) and largest-reachable-at-most-target.

def _cue_reachset(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("subset", "sums to", "reachable sum", "achievable"))


def _fill_reachset(params: list[str], intent: str) -> Iterator[str]:
    nums, target = params
    answers = [f"{target} in _reach",
               f"max(_r for _r in _reach if _r <= {target})",
               "len(_reach)"]
    for ans in answers:
        yield (
            f"_reach = {{0}}\n"
            f"for _x in {nums}:\n"
            f"    _reach = _reach | {{_r + _x for _r in _reach}}\n"
            f"return {ans}"
        )


# --------------------------------------------------------------------- TRAVERSAL (matrix visit orders)
# Scaffold: a matrix visit, with the ORDER as the hole (spiral via direction-cycle + shrinking bounds,
# or row-major / column-major / reverse-column via comprehension). Reaches spiral order and the other
# canonical matrix orders.

def _cue_traversal(params: list[str], intent: str) -> bool:
    return len(params) == 1 and _has(intent, ("spiral", "matrix", "row-major", "column-major",
                                              "row major", "column major"))


def _fill_traversal(params: list[str], intent: str) -> Iterator[str]:
    m = params[0]
    spiral = (
        f"if not {m}:\n    return []\n_res = []\n"
        f"_top, _bot = 0, len({m}) - 1\n_left, _right = 0, len({m}[0]) - 1\n"
        f"while _top <= _bot and _left <= _right:\n"
        f"    for _c in range(_left, _right + 1):\n        _res.append({m}[_top][_c])\n    _top += 1\n"
        f"    for _r in range(_top, _bot + 1):\n        _res.append({m}[_r][_right])\n    _right -= 1\n"
        f"    if _top <= _bot:\n        for _c in range(_right, _left - 1, -1):\n"
        f"            _res.append({m}[_bot][_c])\n        _bot -= 1\n"
        f"    if _left <= _right:\n        for _r in range(_bot, _top - 1, -1):\n"
        f"            _res.append({m}[_r][_left])\n        _left += 1\nreturn _res"
    )
    row_major = f"return [_v for _row in {m} for _v in _row]"
    col_major = (f"if not {m}:\n    return []\n"
                 f"return [{m}[_r][_c] for _c in range(len({m}[0])) for _r in range(len({m}))]")
    rev_col = (f"if not {m}:\n    return []\n"
               f"return [{m}[_r][_c] for _c in range(len({m}[0])) for _r in range(len({m}) - 1, -1, -1)]")
    for body in (spiral, row_major, col_major, rev_col):
        yield body


# --------------------------------------------------------------------- KEYED-STORE-SIM (cache policy)
# Scaffold: replay an ops sequence over a keyed store with a capacity bound. Hole: the eviction policy
# (LRU | FIFO). Reaches LRU-cache simulation and FIFO-cache simulation.

def _cue_keyedstore(params: list[str], intent: str) -> bool:
    return len(params) == 2 and _has(intent, ("cache", "lru", "fifo", "eviction", "evict"))


def _fill_keyedstore(params: list[str], intent: str) -> Iterator[str]:
    cap, ops = params
    lru = (
        f"_cache = {{}}\n_order = []\n_out = []\n"
        f"for _op in {ops}:\n"
        f"    if _op[0] == 'put':\n        _, _k, _val = _op\n"
        f"        if _k in _cache:\n            _order.remove(_k)\n"
        f"        elif len(_cache) >= {cap}:\n            del _cache[_order.pop(0)]\n"
        f"        _cache[_k] = _val\n        _order.append(_k)\n"
        f"    else:\n        _, _k = _op\n"
        f"        if _k in _cache:\n            _order.remove(_k)\n            _order.append(_k)\n"
        f"            _out.append(_cache[_k])\n        else:\n            _out.append(-1)\n"
        f"return _out"
    )
    fifo = (
        f"_cache = {{}}\n_order = []\n_out = []\n"
        f"for _op in {ops}:\n"
        f"    if _op[0] == 'put':\n        _, _k, _val = _op\n"
        f"        if _k not in _cache and len(_cache) >= {cap}:\n            del _cache[_order.pop(0)]\n"
        f"        if _k not in _cache:\n            _order.append(_k)\n        _cache[_k] = _val\n"
        f"    else:\n        _, _k = _op\n        _out.append(_cache.get(_k, -1))\n"
        f"return _out"
    )
    for body in (lru, fifo):
        yield body


@dataclass(frozen=True)
class Schema:
    id: str
    cue: Callable[[list[str], str], bool]
    fill: Callable[..., Iterator[str]]
    needs_examples: bool = False


SCHEMAS: list[Schema] = [
    Schema("dp2d", _cue_dp2d, _fill_dp2d),
    Schema("topo", _cue_topo, _fill_topo),
    Schema("dp1d", _cue_dp1d, _fill_dp1d),
    Schema("backtrack", _cue_backtrack, _fill_backtrack),
    Schema("greedy", _cue_greedy, _fill_greedy),
    Schema("graph", _cue_graph, _fill_graph),
    Schema("scanrun", _cue_scanrun, _fill_scanrun),
    Schema("groupby", _cue_groupby, _fill_groupby),
    Schema("stackscan", _cue_stackscan, _fill_stackscan),
    Schema("valuemap", _cue_valuemap, _fill_valuemap, needs_examples=True),
    Schema("dpstring", _cue_dpstring, _fill_dpstring),
    Schema("reachset", _cue_reachset, _fill_reachset),
    Schema("traversal", _cue_traversal, _fill_traversal),
    Schema("keyedstore", _cue_keyedstore, _fill_keyedstore),
]

SCHEMA_BUDGET_PER = 4000        # hard cap on instantiations per schema (all grammars are far smaller)


def schema_candidates(params: list[str], intent: str, examples: tuple = (),
                      budget_per: int = SCHEMA_BUDGET_PER) -> Iterator[tuple[str, str]]:
    """Yield (schema_id, candidate_body) for every schema whose cue matches the task shape, capped
    per schema. ``examples`` are the task's parsed (args, expected) pairs, used by schemas that learn
    content from data (VALUE-MAP). The caller runs each body through the isolated verifier; nothing
    here is trusted."""
    for schema in SCHEMAS:
        if not schema.cue(params, intent):
            continue
        gen = schema.fill(params, intent, examples) if schema.needs_examples else schema.fill(params, intent)
        count = 0
        for body in gen:
            if count >= budget_per:
                break
            count += 1
            yield schema.id, body
