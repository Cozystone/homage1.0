# -*- coding: utf-8 -*-
"""Schema induction (L3) — the layer that INVENTS algorithm laws instead of applying given ones.

Where ``algorithm_schemas.py`` is a set of laws a human WROTE, this module derives new laws from
ATANOR's own verified solutions. The pipeline (canonical design docs/ATANOR_schema_induction_L3_design.md):

  1. NORMALIZE   — parse each verified library body to an AST; alpha-rename locals to positional slots
                   ``_v{i}`` so bodies that differ only in local names align; keep params ``_a{i}``.
  2. ANTI-UNIFY  — the invention machine. Plotkin's least-general-generalization over the normalized
                   ASTs of a family: the shared skeleton is kept, the positions where members DIFFER
                   become typed HOLES. This is where a law is invented from examples.
  3. MDL RANK    — score a candidate by compression gain = Sum len(without) - [len(schema) + Sum
                   len(via)]. A schema that does not compress the corpus is not a useful abstraction.
  4. VERIFY GATE — OUR floor, absent from DreamCoder/babble: a candidate is promoted ONLY if, treated
                   as a real schema (skeleton + hole enumeration), it re-solves >= K of its source
                   tasks AND generalizes to >= 1 held-out task, every body re-certified by the EXISTING
                   isolated verifier (code_author._certify). Compression alone never promotes.
  5. WAKE-SLEEP  — induce_and_promote() runs 2-4 over the current corpus and adds survivors to an
                   induced-schema store; code_author consults it AFTER the hand schemas. v2 makes this
                   ITERATIVE: WAKE authors a batch (mastery tasks + auto-generated near-variants that
                   populate >= 2 exemplars per family), SLEEP induces + verification-gated promotes,
                   repeated R rounds; each round's survivors enrich the next wake. The grown corpus is
                   persisted default-inert to data/code_reason/ (never auto-loaded into production).

BINDING doctrine: invention is free, SURVIVAL requires verification. No induced schema that fails the
isolated verifier ever ships; honest abstention is preserved; the fabrication floor (fail==0) holds.

v2 lifts holes from EXPRESSION positions to STATEMENTS and control structure: a hole may now be a whole
statement, a block body, a loop-body pattern, or a guard — not just a subexpression. The normalizer
canonicalizes control flow so two solutions that differ by a statement (a fold with an extra guard,
two loops with different bodies) still anti-unify to a scaffold with a STATEMENT hole. Soundness is
unchanged: any induced schema (expression- or statement-holed) must still re-instantiate and pass the
EXISTING isolated verifier; a statement-level generalization that cannot be soundly filled DECLINES
(the engine never emits an unsound law). The v1 boundary — DP-1D unreinvented because the corpus held
only one sibling — is lifted by wake-sleep growth, not by weakening the gate.
"""
from __future__ import annotations

import ast
import itertools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from packages.code_reason import code_author as ca
from packages.code_reason.authorship_harness import Task

REPO = Path(__file__).resolve().parents[2]
# Induced-schema store. Default path intentionally may-not-exist: with no store, induced_candidates
# yields nothing and code_author is unchanged, so the whole engine degrades to exactly L1/L2.
INDUCED_STORE = REPO / "data" / "code_reason" / "induced_schemas.jsonl"
# Wake-sleep grown corpus (v2). DEFAULT-INERT: production's induced_candidates reads INDUCED_STORE
# only, so this file never changes the shipped engine unless LOAD_GROWN is explicitly enabled.
GROWN_CORPUS = REPO / "data" / "code_reason" / "grown_corpus.jsonl"
LOAD_GROWN = False                  # opt-in flag: when True, induced_candidates also consults GROWN_CORPUS

K_RESOLVE = 2                       # a schema must re-solve at least this many of its source tasks
MAX_HOLES = 6                       # a candidate with more divergence than this is not a clean law
FILL_BUDGET = 4000                  # cap on candidate bodies enumerated per schema instantiation

_HOLE_RE = re.compile(r"__HOLE(\d+)__")      # expression hole token
_SHOLE_RE = re.compile(r"__SHOLE(\d+)__")    # statement hole token (v2)
_ANYHOLE_RE = re.compile(r"__S?HOLE(\d+)__")  # either kind
_MISMATCH = object()                # au sentinel: two subtrees cannot be aligned even at a stmt slot


# ============================================================================ 1. NORMALIZE

def _preorder(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _preorder(child)


def _local_names(module: ast.Module) -> list[str]:
    """Names BOUND in the body (assignment / for / comprehension targets, nested def names + args) in
    order of first appearance. Params ``_a{i}`` are only ever loaded, so they are never in this set."""
    seen: dict[str, None] = {}
    for n in _preorder(module):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            seen.setdefault(n.id, None)
        elif isinstance(n, ast.FunctionDef):
            seen.setdefault(n.name, None)
            for a in list(n.args.posonlyargs) + list(n.args.args) + list(n.args.kwonlyargs):
                seen.setdefault(a.arg, None)
    return list(seen)


def normalize_body(template: str) -> ast.Module:
    """Parse a verified body and alpha-rename its locals to ``_v{i}`` (first-appearance order). The
    result is a canonical AST in which two solutions of the same family differ only where their
    ALGORITHM differs, not where a variable happens to be named ``counts`` vs ``freq``."""
    module = ast.parse(template)
    mapping = {name: f"_v{i}" for i, name in enumerate(_local_names(module))}
    for n in ast.walk(module):
        if isinstance(n, ast.Name) and n.id in mapping:
            n.id = mapping[n.id]
        elif isinstance(n, ast.FunctionDef) and n.name in mapping:
            n.name = mapping[n.name]
        elif isinstance(n, ast.arg) and n.arg in mapping:
            n.arg = mapping[n.arg]
    ast.fix_missing_locations(module)
    return module


def _normalized_src(template: str) -> str:
    return ast.unparse(normalize_body(template))


# ============================================================================ 2. ANTI-UNIFY

def _is_hole(node: Any) -> bool:
    """An EXPRESSION hole: a Name whose id is ``__HOLE{n}__``."""
    return isinstance(node, ast.Name) and node.id.startswith("__HOLE")


def _is_stmt_hole(node: Any) -> bool:
    """A STATEMENT hole (v2): an expression-statement wrapping a ``__SHOLE{n}__`` name, so it occupies
    a whole statement slot and unparses to a single ``__SHOLE{n}__`` line."""
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Name)
            and node.value.id.startswith("__SHOLE"))


def _hole_id(node: ast.Name) -> int:
    return int(_HOLE_RE.match(node.id).group(1))


def _stmt_hole_id(node: ast.Expr) -> int:
    return int(_SHOLE_RE.match(node.value.id).group(1))


class _Counter:
    """Shared id space for expression and statement holes, so every hole in one schema has a unique id
    regardless of kind (the id, not the token prefix, keys the fillers dict)."""

    def __init__(self) -> None:
        self.n = 0

    def fresh(self) -> ast.Name:
        h = ast.Name(id=f"__HOLE{self.n}__", ctx=ast.Load())
        self.n += 1
        return h

    def fresh_stmt(self) -> ast.Expr:
        h = ast.Expr(value=ast.Name(id=f"__SHOLE{self.n}__", ctx=ast.Load()))
        self.n += 1
        return h


def _au(a: Any, b: Any, ctr: _Counter) -> Any:
    """Plotkin anti-unification of two AST nodes -> the least-general skeleton. Equal structure is
    kept; divergence at an EXPRESSION slot becomes an expression hole; divergence between two whole
    STATEMENTS at the same block position becomes a statement hole (v2); divergence at an operator, or
    an unalignable block, returns _MISMATCH. Holes already present in ``a`` (from a previous fold)
    absorb whatever ``b`` has there — expression holes and statement holes alike."""
    if _is_stmt_hole(a):
        return a                                # a statement hole absorbs any statement at this slot
    if _is_hole(a):
        return a
    if type(a) is not type(b):
        return _MISMATCH
    if not isinstance(a, ast.AST):
        return a if a == b else _MISMATCH
    if isinstance(a, ast.Constant):
        return a if (type(a.value) is type(b.value) and a.value == b.value) else _MISMATCH
    fields: dict[str, Any] = {}
    for f in a._fields:
        r = _au_field(getattr(a, f, None), getattr(b, f, None), ctr)
        if r is _MISMATCH:
            return _MISMATCH
        fields[f] = r
    node = type(a)(**fields)
    return node


def _au_field(va: Any, vb: Any, ctr: _Counter) -> Any:
    if isinstance(va, ast.AST) and isinstance(vb, ast.AST):
        r = _au(va, vb, ctr)
        if r is _MISMATCH:
            # A divergence here becomes a hole ONLY if this slot holds an expression; a statement or
            # operator divergence propagates up (v1 does not invent statement-level holes).
            return ctr.fresh() if isinstance(va, ast.expr) else _MISMATCH
        return r
    if isinstance(va, list) and isinstance(vb, list):
        # Equal-length lists (statement blocks or argument lists): align element-wise. An expression
        # element that diverges becomes an expression hole; two whole STATEMENTS that diverge (e.g. a
        # bare accumulate vs the same accumulate under a guard) become a statement hole (v2).
        if len(va) == len(vb):
            out = []
            for xa, xb in zip(va, vb):
                if isinstance(xa, ast.AST) and isinstance(xb, ast.AST):
                    r = _au(xa, xb, ctr)
                    if r is _MISMATCH:
                        if isinstance(xa, ast.expr) and isinstance(xb, ast.expr):
                            out.append(ctr.fresh())
                        elif isinstance(xa, ast.stmt) and isinstance(xb, ast.stmt):
                            out.append(ctr.fresh_stmt())
                        else:
                            return _MISMATCH
                    else:
                        out.append(r)
                else:
                    if xa != xb:
                        return _MISMATCH
                    out.append(xa)
            return out
        # Unequal-length statement blocks: align the shared prefix/suffix and fold the differing middle
        # run into a SINGLE statement hole, but only when both middles are non-empty pure-statement runs
        # (so the hole is a real block a filler can occupy). Anything else is too incoherent -> MISMATCH.
        if all(isinstance(x, ast.stmt) for x in va) and all(isinstance(x, ast.stmt) for x in vb):
            return _au_stmt_lists(va, vb, ctr)
        return _MISMATCH
    return va if va == vb else _MISMATCH


def _au_stmt_lists(va: list, vb: list, ctr: _Counter) -> Any:
    """Anti-unify two statement blocks of different length: keep the equal-by-unparse shared prefix and
    suffix, replace the divergent middle of each with one statement hole. Returns _MISMATCH if the two
    middles are not both non-empty (nothing to generalize, or a pure deletion) so we never invent a
    hole that some source fills with nothing (which would be unsound)."""
    pa = [ast.unparse(x) for x in va]
    pb = [ast.unparse(x) for x in vb]
    pre = 0
    while pre < len(pa) and pre < len(pb) and pa[pre] == pb[pre]:
        pre += 1
    suf = 0
    while (suf < len(pa) - pre and suf < len(pb) - pre
           and pa[len(pa) - 1 - suf] == pb[len(pb) - 1 - suf]):
        suf += 1
    mid_a = va[pre:len(va) - suf]
    mid_b = vb[pre:len(vb) - suf]
    if not mid_a or not mid_b:
        return _MISMATCH
    return list(va[:pre]) + [ctr.fresh_stmt()] + list(va[len(va) - suf:] if suf else [])


def _extract_fillers(skel: Any, src: Any, out: dict[int, str]) -> None:
    """Walk the skeleton against one original source; at each hole record that source's subtree text.
    Expression holes record an expression; statement holes record a whole statement (or, for an
    unequal-length block, the joined middle run the hole stands in for)."""
    if _is_stmt_hole(skel):
        out[_stmt_hole_id(skel)] = ast.unparse(src) if isinstance(src, ast.AST) else str(src)
        return
    if _is_hole(skel):
        out[_hole_id(skel)] = ast.unparse(src) if isinstance(src, ast.AST) else str(src)
        return
    if not isinstance(skel, ast.AST):
        return
    for f in skel._fields:
        sv, dv = getattr(skel, f, None), getattr(src, f, None)
        if isinstance(sv, ast.AST) and isinstance(dv, ast.AST):
            _extract_fillers(sv, dv, out)
        elif isinstance(sv, list) and isinstance(dv, list):
            _extract_list_fillers(sv, dv, out)


def _extract_list_fillers(skel: list, src: list, out: dict[int, str]) -> None:
    """Align a skeleton statement/expr list against a source list. Equal lengths align 1:1. When the
    skeleton contains a single statement hole and the lengths differ, the hole absorbs the source's
    MIDDLE run (the statements between the shared prefix and suffix), recorded as joined source text."""
    if len(skel) == len(src):
        for a, b in zip(skel, src):
            if isinstance(a, ast.AST) and isinstance(b, ast.AST):
                _extract_fillers(a, b, out)
        return
    hole_idxs = [i for i, x in enumerate(skel) if _is_stmt_hole(x)]
    if len(hole_idxs) != 1:
        return
    hi = hole_idxs[0]
    pre, suf = hi, len(skel) - hi - 1
    for a, b in zip(skel[:pre], src[:pre]):
        if isinstance(a, ast.AST) and isinstance(b, ast.AST):
            _extract_fillers(a, b, out)
    middle = src[pre:len(src) - suf]
    out[_stmt_hole_id(skel[hi])] = "\n".join(ast.unparse(x) for x in middle)
    if suf:
        for a, b in zip(skel[hi + 1:], src[len(src) - suf:]):
            if isinstance(a, ast.AST) and isinstance(b, ast.AST):
                _extract_fillers(a, b, out)


@dataclass
class CandidateSchema:
    family: str
    arity: int
    skeleton_src: str                       # normalized template with ``__HOLE{i}__`` tokens
    holes: dict[int, list[str]]             # hole id -> observed filler per source (source order)
    templates: list[str]                    # the normalized source bodies (for MDL)
    cue_tokens: list[str] = field(default_factory=list)

    @property
    def n_holes(self) -> int:
        return len(self.holes)

    def mdl_gain(self) -> float:
        """Compression gain per the design formula: without - [schema + via]. Positive means the
        schema pays for itself over the corpus it explains."""
        without = sum(len(t) for t in self.templates)
        schema = len(self.skeleton_src)
        via = 0
        for i in range(len(self.templates)):
            via += sum(len(self.holes[h][i]) for h in self.holes if i < len(self.holes[h]))
        return without - (schema + via)

    def fill(self, params: list[str], intent: str = "", examples: tuple = (),
             budget: int = FILL_BUDGET) -> Iterator[str]:
        yield from _fill(self.skeleton_src, self.holes, self.arity, params, intent, budget)

    def to_spec(self) -> dict[str, Any]:
        return {"family": self.family, "arity": self.arity, "skeleton": self.skeleton_src,
                "holes": {str(k): v for k, v in self.holes.items()},
                "templates": self.templates, "cue_tokens": self.cue_tokens,
                "mdl_gain": round(self.mdl_gain(), 2), "n_holes": self.n_holes}


def anti_unify(templates: list[str], *, family: str = "induced", intents: list[str] | None = None,
               arity: int | None = None) -> CandidateSchema | None:
    """Invent a candidate schema by anti-unifying >= 2 normalized solutions. Returns None when the
    family does not align at expression granularity (statement-structure divergence) or collapses to
    an all-hole body (no shared structure worth abstracting)."""
    if len(templates) < 2:
        return None
    norm = [normalize_body(t) for t in templates]
    ctr = _Counter()
    skel = norm[0]
    for nxt in norm[1:]:
        skel = _au(skel, nxt, ctr)
        if skel is _MISMATCH:
            return None
    if ctr.n == 0 or ctr.n > MAX_HOLES:
        return None                                     # nothing diverged, or too incoherent to be a law
    try:
        ast.fix_missing_locations(skel)
        skeleton_src = ast.unparse(skel)
    except (ValueError, AttributeError):
        return None
    if _ANYHOLE_RE.sub("_", skeleton_src).strip() in ("", "return _", "_"):
        return None                                     # whole body is a hole -> not an abstraction
    # STATEMENT-HOLE COHERENCE (v2): a genuine statement-level law has the statement hole as its ONE
    # dominant locus of variation (at most one accompanying expression hole, e.g. a shared-but-varying
    # init). When a statement hole coexists with many expression holes, the members share only loop
    # scaffolding, not an algorithm (coin_change vs subset_sum: init, iterable, body AND answer all
    # diverge) -> decline rather than emit a hollow "generic loop" that memorizes two algorithms. This
    # guard fires only when a statement hole is present, so v1's expression-only schemas are unchanged.
    if _SHOLE_RE.search(skeleton_src) and ctr.n > 2:
        return None
    holes: dict[int, list[str]] = {}
    norm_srcs = [ast.unparse(m) for m in norm]
    for m in norm:
        single: dict[int, str] = {}
        _extract_fillers(skel, m, single)
        for hid, filler in single.items():
            holes.setdefault(hid, []).append(filler)
    if len(holes) != ctr.n:                             # a hole no source could fill -> unsound
        return None
    cue: list[str] = []
    for it in (intents or []):
        for tok in ca._verbs(it):
            if tok not in cue:
                cue.append(tok)
    return CandidateSchema(family=family, arity=arity if arity is not None else 0,
                           skeleton_src=skeleton_src, holes=holes, templates=norm_srcs, cue_tokens=cue)


# ============================================================================ hole filling (shared)

def _is_simple_expr(fillers: list[str]) -> bool:
    """A hole whose observed fillers are all short single-line expressions may be widened with the
    existing expression grammar (type-directed generalization); a hole holding a complex multi-clause
    expression is left to its observed fillers only."""
    return all(("\n" not in f and len(f) <= 40) for f in fillers)


def _type_directed(skeleton_src: str, arity: int, intent: str, limit: int = 30) -> list[str]:
    """Reuse code_author's EXPRESSION families over the schema's in-scope variables (its ``_v`` locals
    and ``_a`` params) — a hole can be filled by any expression the base engine already knows how to
    build. This is how an induced schema GENERALIZES to a held-out task that needs a filler none of
    the sources used (e.g. count-dict -> ``len(_v0)`` for a distinct-count task)."""
    variables = sorted(set(re.findall(r"_v\d+", skeleton_src))) + [f"_a{i}" for i in range(arity)]
    out: list[str] = []
    for var in variables:
        for fam in ca.EXPR_FAMILIES:
            for expr in fam([var], intent):
                if expr not in out:
                    out.append(expr)
                    if len(out) >= limit * max(1, len(variables)):
                        break
    return out[: limit * max(1, len(variables))]


def _is_stmt_hole_id(skeleton_src: str, hid: int) -> bool:
    return f"__SHOLE{hid}__" in skeleton_src


def _names_in(fillers: list[str], pat: str) -> list[str]:
    seen: dict[str, None] = {}
    for f in fillers:
        for m in re.findall(pat, f):
            seen.setdefault(m, None)
    return list(seen)


def _stmt_grammar(observed: list[str], skeleton_src: str, limit: int = 48) -> list[str]:
    """Type-directed generalization for a STATEMENT hole. From the accumulator/loop variables the
    observed fillers actually use (parsed from their own text), enumerate a small statement grammar —
    bare and guarded accumulate/aug-assign/append — so the schema GENERALIZES to a novel task whose
    body-statement none of the sources used (e.g. sum-of-positives -> sum-of-negatives via a new
    guard). Every candidate is still isolated-verified, so an unsound statement is simply rejected."""
    # Accumulator = a name assigned inside a filler (LHS of '=' or target of aug-assign); loop/element
    # vars = the _v/_a names the fillers read. Grounding the grammar in the family's own names keeps it
    # in-scope (a statement referencing an unbound name just fails to verify).
    accs: list[str] = []                                                    # scalar (assignment) accumulators
    for f in observed:
        for m in re.findall(r"(_[va]\d+)\s*(?:[-+*/]?=)", f):
            if m not in accs:
                accs.append(m)
    list_accs: list[str] = []                                               # list (append) accumulators
    for f in observed:
        for m in re.findall(r"(_[va]\d+)\.append\(", f):
            if m not in list_accs:
                list_accs.append(m)
    allnames = _names_in(observed, r"_[va]\d+")
    loops = [n for n in allnames if n not in accs and n not in list_accs] or allnames
    if not accs and not list_accs:
        return []
    out: list[str] = []

    def add(s: str) -> None:
        if s not in out and s not in observed:
            out.append(s)

    guards = ["{L} > 0", "{L} < 0", "{L} % 2 == 0", "{L} % 2 != 0", "{L} != 0"]
    for A in accs[:2]:
        for L in loops[:2]:
            for op in ("+", "*", "-"):
                add(f"{A} = {A} {op} {L}")                                   # bare fold
                for g in guards:
                    add(f"if {g.format(L=L)}:\n    {A} = {A} {op} {L}")      # guarded fold (any op)
            add(f"{A} = {A} + 1")
            for g in guards:
                add(f"if {g.format(L=L)}:\n    {A} = {A} + 1")               # guarded count
    for A in list_accs[:2]:
        for L in loops[:2]:
            add(f"{A}.append({L})")                                          # bare collect
            for g in guards:
                add(f"if {g.format(L=L)}:\n    {A}.append({L})")             # guarded collect
    return out[:limit]


def _fill(skeleton_src: str, holes: dict[int, list[str]], arity: int, params: list[str],
          intent: str, budget: int) -> Iterator[str]:
    hole_ids = sorted(holes)
    stmt_kind = [_is_stmt_hole_id(skeleton_src, hid) for hid in hole_ids]

    def build(combo: tuple[str, ...]) -> str:
        body = skeleton_src
        for hid, is_stmt, filler in zip(hole_ids, stmt_kind, combo):
            body = _replace_stmt_hole(body, hid, filler) if is_stmt else body.replace(f"__HOLE{hid}__", filler)
        return ca._instantiate(body, params)

    tried = 0
    seen: set[tuple[str, ...]] = set()
    # (1) SOURCE DIAGONALS first: reconstruct each original body (hole i-th filler across all holes), so a
    # schema re-solves every one of its N sources within a handful of tries — independent of how large the
    # type-directed generalization set below is. (This is the property _resolve_count needs to see K sources
    # re-solved even when a source's fillers sit deep in the cartesian order.)
    n_sources = max((len(v) for v in holes.values()), default=0)
    for i in range(n_sources):
        combo = tuple(holes[hid][i] if i < len(holes[hid]) else holes[hid][-1] for hid in hole_ids)
        if combo in seen:
            continue
        seen.add(combo)
        tried += 1
        yield build(combo)
        if tried >= budget:
            return
    # (2) TYPE-DIRECTED product for GENERALIZATION to a held-out task needing a filler no source used.
    per_hole: list[list[str]] = []
    extra = _type_directed(skeleton_src, arity, intent)
    for hid in hole_ids:
        observed = list(dict.fromkeys(holes[hid]))
        options = list(observed)
        if _is_stmt_hole_id(skeleton_src, hid):
            for s in _stmt_grammar(observed, skeleton_src):
                if s not in options:
                    options.append(s)
        elif _is_simple_expr(observed):
            for e in extra:
                if e not in options:
                    options.append(e)
        per_hole.append(options)
    for combo in itertools.product(*per_hole):
        if tried >= budget:
            return
        if combo in seen:
            continue
        seen.add(combo)
        tried += 1
        yield build(combo)


def _replace_stmt_hole(body: str, hid: int, filler: str) -> str:
    """Substitute a (possibly multi-line) statement filler for a ``__SHOLE{hid}__`` placeholder line,
    re-indenting every filler line by the placeholder's own leading whitespace so block nesting and the
    filler's internal indentation are both preserved (sound Python out)."""
    token = f"__SHOLE{hid}__"
    lines_out: list[str] = []
    fill_lines = filler.splitlines() or [""]
    for line in body.splitlines():
        idx = line.find(token)
        if idx != -1 and line.strip() == token:
            indent = line[:idx]
            for fl in fill_lines:
                lines_out.append(indent + fl if fl else fl)
        else:
            lines_out.append(line)
    return "\n".join(lines_out)


# ============================================================================ 3-4. RANK + VERIFY GATE

def _resolve_count(schema: CandidateSchema, tasks: list[Task]) -> int:
    """How many source tasks the schema re-solves through the isolated verifier."""
    solved = 0
    for t in tasks:
        params = ca._params(t.signature)
        if _solve_via(schema, t, params):
            solved += 1
    return solved


def _solve_via(schema: CandidateSchema, task: Task, params: list[str]) -> str | None:
    """First schema instantiation that passes the isolated verifier for ``task``, or None. Fast
    in-process filter first, then the real isolated oracle — exactly code_author's two-tier gate."""
    for body in schema.fill(params, task.docstring):
        if ca._run_fast(task, body) and ca._certify(task, body):
            return body
    return None


def _solve_via_full(schema: CandidateSchema, task: Task) -> bool:
    """Generalization probe: the instantiation must pass the task's FULL test (visible + held-out
    hidden inputs). A body that fits the visible examples but fails hidden is over-fit and rejected."""
    from dataclasses import replace
    params = ca._params(task.signature)
    full = task.test + ("\n" + task.hidden if task.hidden else "")
    probe = replace(task, test=full)
    for body in schema.fill(params, task.docstring):
        if ca._run_fast(probe, body) and ca._certify(probe, body):
            return True
    return False


def promote(schema: CandidateSchema, source_tasks: list[Task], holdout_tasks: list[Task],
            k: int = K_RESOLVE) -> dict[str, Any]:
    """The floor. A candidate is accepted ONLY if it re-solves >= k source tasks AND generalizes to
    >= 1 held-out task, every body re-certified by the isolated verifier. Positive MDL is necessary
    (a useless abstraction is not promoted) but NOT sufficient — verification decides."""
    gain = schema.mdl_gain()
    resolved = _resolve_count(schema, source_tasks)
    generalized = sum(1 for t in holdout_tasks if _solve_via_full(schema, t))
    accepted = bool(gain > 0 and resolved >= k and generalized >= 1)
    return {"family": schema.family, "mdl_gain": round(gain, 2), "resolved": resolved,
            "n_sources": len(source_tasks), "generalized": generalized,
            "n_holdout": len(holdout_tasks), "accepted": accepted, "n_holes": schema.n_holes,
            "skeleton": schema.skeleton_src}


# ============================================================================ induced-schema store

_STORE_CACHE: dict[str, Any] = {"path": None, "mtime": None, "specs": []}


def load_induced() -> list[dict[str, Any]]:
    path = INDUCED_STORE
    if not path.exists():
        _STORE_CACHE.update(path=str(path), mtime=None, specs=[])
        return []
    mtime = path.stat().st_mtime
    if _STORE_CACHE["path"] == str(path) and _STORE_CACHE["mtime"] == mtime:
        return _STORE_CACHE["specs"]
    specs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
                r["holes"] = {int(k): v for k, v in r["holes"].items()}
                specs.append(r)
            except Exception:
                continue
    _STORE_CACHE.update(path=str(path), mtime=mtime, specs=specs)
    return specs


def save_induced(specs: list[dict[str, Any]]) -> None:
    INDUCED_STORE.parent.mkdir(parents=True, exist_ok=True)
    with INDUCED_STORE.open("w", encoding="utf-8") as f:
        for s in specs:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    _STORE_CACHE.update(path=None, mtime=None, specs=[])     # invalidate


def load_grown() -> list[dict[str, Any]]:
    """Load the wake-sleep grown corpus of laws (default-inert store). Never consulted by production
    unless ``LOAD_GROWN`` is set — so growing the corpus can never silently change the shipped engine."""
    path = GROWN_CORPUS
    if not path.exists():
        return []
    specs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
                r["holes"] = {int(k): v for k, v in r["holes"].items()}
                specs.append(r)
            except Exception:
                continue
    return specs


def save_grown(specs: list[dict[str, Any]]) -> None:
    """Persist the grown corpus of laws to a data/code_reason/ file. Default-inert: production reads it
    only when LOAD_GROWN is explicitly enabled."""
    GROWN_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with GROWN_CORPUS.open("w", encoding="utf-8") as f:
        for s in specs:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def induced_candidates(params: list[str], intent: str, examples: tuple = (),
                       budget: int = FILL_BUDGET) -> Iterator[tuple[str, str]]:
    """Consulted by code_author AFTER the hand schemas: yield (family_id, candidate_body) for every
    induced schema whose arity matches the task. Structural (arity) applicability — not the brittle
    keyword cue of a hand schema — is the point: an induced law fires on a task whose wording a hand
    cue would miss, and the verifier still gates everything (fail stays 0)."""
    arity = len(params)
    specs = load_induced() + (load_grown() if LOAD_GROWN else [])   # grown corpus opt-in only
    # PER-LAW budget: each applicable induced law gets its own share so an earlier law (e.g. the induced
    # DP-2D scaffold) can never STARVE a later one (the grown DP-1D law) on a task both are arity-eligible
    # for. Diagonals come first inside _fill, so each law's own source reconstructions are tried promptly.
    for spec in specs:
        if spec.get("arity") != arity:
            continue
        emitted = 0
        for body in _fill(spec["skeleton"], spec["holes"], arity, params, intent, budget):
            emitted += 1
            if emitted > budget:
                break
            yield spec["family"], body


# ============================================================================ 5. WAKE-SLEEP

def _authored_templates(tasks: list[Task]) -> dict[str, tuple[str, Task]]:
    """WAKE: author each task with the current hand engine, returning the verified body normalized to
    ``_a{i}`` form (the induction material) keyed by task name. Tasks the engine cannot solve are
    simply absent — induction only ever abstracts REAL verified solutions."""
    out: dict[str, tuple[str, Task]] = {}
    for t in tasks:
        a = ca.author(t)
        if a.verified and a.body:
            out[t.name] = (ca._normalize(a.body, ca._params(t.signature)), t)
    return out


def _coarse_signature(template: str) -> tuple:
    try:
        m = ast.parse(_normalized_src(template))
    except SyntaxError:
        return ("bad",)
    return (len(m.body), tuple(type(s).__name__ for s in m.body))


def _cluster(items: list[tuple[str, Task]]) -> list[list[tuple[str, Task]]]:
    """Greedy clustering inside a coarse group: a member joins a cluster only if anti-unifying it with
    the cluster keeps a clean, positive-MDL, few-hole schema. This separates e.g. count-dict folds
    from anagram folds even though both are (Assign, For, Return)."""
    clusters: list[list[tuple[str, Task]]] = []
    for tmpl, task in items:
        placed = False
        for cl in clusters:
            trial = [t for t, _ in cl] + [tmpl]
            sch = anti_unify(trial, arity=len(ca._params(task.signature)))
            if sch is not None and sch.mdl_gain() > 0 and sch.n_holes <= MAX_HOLES:
                cl.append((tmpl, task))
                placed = True
                break
        if not placed:
            clusters.append([(tmpl, task)])
    return clusters


# ---- WAKE: near-variant task generation (populate under-filled families to >= 2 exemplars) --------

def _count_change_ways_task() -> Task:
    """A genuine SECOND DP-1D task (near-variant of coin_change): ordered change-counting. It fits the
    same linear-DP scaffold but pins DIFFERENT holes — seed dp[0]=1, rest 0, additive recurrence — so
    coin_change + this pair anti-unifies to the DP-1D law with the whole table-fill owned. Visible
    examples are discriminating (they exclude the min-coin instantiation), so the engine stores the
    additive body, not a coincidental fit."""
    return Task("count_change_ways", "def count_change_ways(coins, amount):",
                "Return the number of ordered ways to make change for amount using the given coins.",
                "assert count_change_ways([1, 2], 3) == 3\nassert count_change_ways([1, 2], 4) == 5\n"
                "assert count_change_ways([2], 3) == 0\nassert count_change_ways([1], 5) == 1\n"
                "assert count_change_ways([1, 2], 0) == 1",
                reference=("dp = [1] + [0] * amount\nfor k in range(1, amount + 1):\n"
                           "    for c in coins:\n        if c <= k:\n            dp[k] = dp[k] + dp[k - c]\n"
                           "return dp[amount]"),
                hidden="assert count_change_ways([1, 2, 3], 4) == 7\nassert count_change_ways([3], 4) == 0")


def _fold_task(name: str, doc: str, examples: str, ref: str, hidden: str) -> Task:
    return Task(name, f"def {name}(xs):", doc, examples, reference=ref, hidden=hidden)


def _accumulate_pool() -> list[Task]:
    """Scalar-fold near-variants that the accumulate block family authors as loop bodies differing by a
    single STATEMENT (bare fold vs guarded fold) — the material for statement-level anti-unification."""
    return [
        _fold_task("product_all", "Return the product of all numbers in xs.",
                   "assert product_all([1, 2, 3, 4]) == 24\nassert product_all([5]) == 5\n"
                   "assert product_all([]) == 1\nassert product_all([2, 3]) == 6",
                   "p = 1\nfor x in xs:\n    p = p * x\nreturn p",
                   "assert product_all([2, 2, 2]) == 8\nassert product_all([-1, 4]) == -4"),
        _fold_task("product_positive", "Return the product of the positive numbers in xs.",
                   "assert product_positive([1, 2, -3, 4]) == 8\nassert product_positive([-1, -2]) == 1\n"
                   "assert product_positive([2, 3]) == 6\nassert product_positive([]) == 1",
                   "p = 1\nfor x in xs:\n    if x > 0:\n        p = p * x\nreturn p",
                   "assert product_positive([5, -5, 2]) == 10"),
    ]


def _wake_pool() -> list[Task]:
    """Curated genuine near-variants of solved tasks that populate under-filled families to >= 2 clean
    exemplars: count_change_ways (the DP-1D family's missing sibling) and a product / product-of-
    positives pair (the accumulate statement-hole family). Each is well-posed (its reference passes
    visible + hidden), so a wake solve is real synthesis, never a hand-fed answer."""
    return [_count_change_ways_task()] + _accumulate_pool()


def _eval_body(signature: str, body: str, args: tuple) -> Any:
    """Run a verified body on fresh inputs in the same restricted namespace the search uses, to compute
    the expected output for an auto-generated near-variant. Safe only for our own verified bodies."""
    import textwrap
    src = signature + "\n" + textwrap.indent(textwrap.dedent(body).strip(), "    ")
    ns: dict[str, Any] = {"__builtins__": ca._SAFE_BUILTINS}
    exec(compile(src, "<variant>", "exec", optimize=0), ns)
    fname = re.search(r"def\s+(\w+)", signature).group(1)
    return ns[fname](*args)


def _near_variants(tasks: list[Task], per_task: int = 1) -> list[Task]:
    """AUTO-GENERATE near-variants: for a solved task with all-integer example args, perturb the args
    and recompute the expected output by evaluating the task's OWN verified body — a fresh, well-posed
    exemplar of the same family, produced without any human answer. This grows the corpus and library
    (re-solving reinforces a shape); families whose members genuinely differ by a hole still need the
    curated pool, but this is the honest mechanical half of wake growth."""
    out: list[Task] = []
    for t in tasks:
        a = ca.author(t)
        if not (a.verified and a.body):
            continue
        pairs = ca._parse_examples(t)
        made = 0
        for args, _exp in pairs:
            if made >= per_task:
                break
            if not (args and all(isinstance(x, int) for x in args)):
                continue
            new_args = tuple(x + 3 for x in args)
            try:
                exp = _eval_body(t.signature, a.body, new_args)
            except Exception:
                continue
            vname = f"{t.name}__v"
            vsig = t.signature.replace(f"def {t.name}", f"def {vname}", 1)
            call = f"{vname}({', '.join(repr(x) for x in new_args)})"
            out.append(Task(vname, vsig, t.docstring, f"assert {call} == {exp!r}", reference=a.body))
            made += 1
    return out


def _sleep_over(authored: dict[str, tuple[str, Task]], seen_skeletons: set[str]
                ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One SLEEP pass over an already-authored corpus: group + cluster the solutions, anti-unify each
    cluster of >= 2, MDL-rank, and run the verification gate. Returns (candidate reports, survivor
    specs). ``seen_skeletons`` dedups across rounds so a law induced in an earlier round is not
    re-emitted. Generalization is leave-one-out for >= 3 members, else on each member's own held-out
    hidden inputs (unseen, so passing them is real generalization)."""
    groups: dict[tuple, list[tuple[str, Task]]] = {}
    for name, (tmpl, task) in authored.items():
        arity = len(ca._params(task.signature))
        groups.setdefault((arity,) + _coarse_signature(tmpl), []).append((tmpl, task))
    candidates: list[dict[str, Any]] = []
    survivors: list[dict[str, Any]] = []
    for sig, items in groups.items():
        if len(items) < 2:
            continue
        for cluster in _cluster(items):
            if len(cluster) < 2:
                continue
            templates = [t for t, _ in cluster]
            src_tasks = [tk for _, tk in cluster]
            arity = sig[0]
            fam = "+".join(tk.name for tk in src_tasks)[:60]
            schema = anti_unify(templates, family=fam,
                                intents=[tk.docstring for tk in src_tasks], arity=arity)
            if schema is None or schema.skeleton_src in seen_skeletons:
                continue
            seen_skeletons.add(schema.skeleton_src)
            if len(cluster) >= 3:
                holdout = [src_tasks[-1]]
                learn = anti_unify(templates[:-1], family=fam,
                                   intents=[tk.docstring for tk in src_tasks[:-1]], arity=arity) or schema
                rep = promote(learn, src_tasks[:-1], holdout)
                store_schema = schema                      # store the full-corpus schema once accepted
            else:
                rep = promote(schema, src_tasks, src_tasks)   # generalize on own hidden inputs
                store_schema = schema
            candidates.append(rep)
            if rep["accepted"]:
                survivors.append(store_schema.to_spec())
    return candidates, survivors


def induce_and_promote(tasks: list[Task] | None = None, *, persist: bool = True,
                       rounds: int = 1, wake: bool = False) -> dict[str, Any]:
    """Wake-sleep induction. With ``rounds == 1`` and ``wake == False`` this is exactly the v1 sleep
    pass (author the suite once, induce, verification-gate, persist survivors to the induced store).

    v2 makes it ITERATIVE. Each round: WAKE authors the batch (the suite, plus — when ``wake`` — the
    near-variant pool that populates under-filled families to >= 2 exemplars, and auto-generated input
    perturbations of solved tasks); SLEEP induces + promotes; survivors are persisted so the NEXT
    round's authoring can consult them (a law learned in round r can help solve a round r+1 task). All
    survival is verification-gated — nothing that fails the isolated verifier is ever stored."""
    if tasks is None:
        from packages.code_reason.benchmarks.mastery_v1 import all_tasks
        tasks = all_tasks()
    all_candidates: list[dict[str, Any]] = []
    survivors_by_skel: dict[str, dict[str, Any]] = {}
    seen_skeletons: set[str] = set()
    authored_total = 0
    for _r in range(max(1, rounds)):
        batch = list(tasks)
        if wake:
            batch = batch + _wake_pool() + _near_variants(tasks)
        authored = _authored_templates(batch)              # authoring consults already-persisted laws
        authored_total = len(authored)
        cands, survs = _sleep_over(authored, seen_skeletons)
        all_candidates += cands
        for spec in survs:
            survivors_by_skel[spec["skeleton"]] = spec
        if persist and survivors_by_skel:
            save_induced(list(survivors_by_skel.values()))  # enrich for the next round's wake
    survivors = list(survivors_by_skel.values())
    return {"n_tasks": len(tasks), "authored": authored_total, "rounds": max(1, rounds),
            "candidates": len(all_candidates), "promoted": len(survivors),
            "detail": all_candidates, "survivors": [s["family"] for s in survivors]}


def grow_corpus(rounds: int = 2, *, persist: bool = True,
                tasks: list[Task] | None = None) -> dict[str, Any]:
    """Run wake-sleep growth against isolated temp state, compare it to a single STATIC induction, and
    persist the grown laws to the DEFAULT-INERT grown corpus (never auto-loaded into production unless
    LOAD_GROWN is set). The number to read is ``added`` — the families wake-sleep reached that a static
    pass over the fixed library did not (chiefly the DP-1D law, unblocked by its grown second exemplar)."""
    import tempfile
    global INDUCED_STORE
    saved_store, saved_lib = INDUCED_STORE, ca.LIBRARY
    try:
        INDUCED_STORE = Path(tempfile.mkdtemp(prefix="static_ind_")) / "s.jsonl"
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="static_lib_")) / "l.jsonl"
        static = induce_and_promote(tasks=tasks, persist=True, rounds=1, wake=False)
        INDUCED_STORE = Path(tempfile.mkdtemp(prefix="grown_ind_")) / "g.jsonl"
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="grown_lib_")) / "l.jsonl"
        grown = induce_and_promote(tasks=tasks, persist=True, rounds=rounds, wake=True)
        specs = load_induced()                                  # every law after growth
    finally:
        INDUCED_STORE, ca.LIBRARY = saved_store, saved_lib
    if persist and specs:
        save_grown(specs)
    static_fams, grown_fams = set(static["survivors"]), set(grown["survivors"])
    return {"static_promoted": static["promoted"], "grown_promoted": grown["promoted"],
            "added": sorted(grown_fams - static_fams), "rounds": rounds,
            "grown_families": grown["survivors"],
            "persisted_to": str(GROWN_CORPUS) if (persist and specs) else None}


# ============================================================================ 3. HONESTY EXPERIMENT I3

# Each family names the source solutions to induce from, how the corresponding HAND law is ablated,
# the target task to re-solve, and a held-out generalization probe. This is the design's Ablate-and-
# Reinvent instrument: remove the human law, and measure whether the engine reinvents it from the
# solutions it once produced.
def _distinct_count_probe() -> Task:
    return Task("distinct_count", "def distinct_count(s):",
                "Return the number of distinct characters in s.",
                "assert distinct_count('aab') == 2\nassert distinct_count('') == 0\n"
                "assert distinct_count('abc') == 3",
                hidden="assert distinct_count('aaaa') == 1\nassert distinct_count('abcabc') == 3")


def _min_edits_probe() -> Task:
    return Task("min_edits", "def min_edits(x, y):",
                "Return the minimum single-character insert, delete, or substitute operations to turn x into y.",
                "assert min_edits('cat', 'cut') == 1\nassert min_edits('', 'ab') == 2\n"
                "assert min_edits('abc', 'abc') == 0",
                hidden="assert min_edits('sunday', 'saturday') == 3\nassert min_edits('a', '') == 1")


_ABLATION_FAMILIES: dict[str, dict[str, Any]] = {
    "count_dict": {"sources": ["char_frequency", "most_frequent"], "target": "char_frequency",
                   "holdout": _distinct_count_probe, "disable": [("block", "_blk_count_dict")]},
    # Both hand paths to a plain sum are removed, so ablation stays CLEAN: after removal the only route
    # left to `total` is the induced aggregate law (else the accumulate block would answer it and the
    # necessity check would be a lie).
    "aggregate": {"sources": ["total", "maximum", "minimum"], "target": "total",
                  "holdout": None, "disable": [("expr", "_fam_aggregate"), ("block", "_blk_accumulate")]},
    "dp2d": {"sources": ["edit_distance", "longest_common_subsequence"], "target": "edit_distance",
             "holdout": _min_edits_probe, "disable": [("schema", "dp2d")]},
    "dp1d": {"sources": ["coin_change"], "target": "coin_change",
             "holdout": None, "disable": [("schema", "dp1d")]},
}


class _Ablation:
    """Temporarily remove one or more hand laws from the live engine so a re-solve is attributable to
    induction alone, restoring them on exit. Accepts a LIST of (kind, name) disables so a family with
    several hand routes (e.g. sum via both an expression family and the accumulate block) can be
    ablated cleanly in one context."""

    def __init__(self, disables: list[tuple[str, str]]) -> None:
        self.disables = disables
        self._saved: dict[str, Any] = {}

    def __enter__(self):
        import packages.code_reason.algorithm_schemas as sch
        if "expr" not in self._saved:
            self._saved["expr"] = ca.EXPR_FAMILIES[:]
        if "block" not in self._saved:
            self._saved["block"] = ca.BLOCK_FAMILIES[:]
        if "schema" not in self._saved:
            self._saved["schema"] = sch.SCHEMAS[:]
        for kind, name in self.disables:
            if kind == "block":
                ca.BLOCK_FAMILIES[:] = [f for f in ca.BLOCK_FAMILIES if f.__name__ != name]
            elif kind == "expr":
                ca.EXPR_FAMILIES[:] = [f for f in ca.EXPR_FAMILIES if f.__name__ != name]
            elif kind == "schema":
                sch.SCHEMAS[:] = [s for s in sch.SCHEMAS if s.id != name]
        return self

    def __exit__(self, *exc):
        import packages.code_reason.algorithm_schemas as sch
        ca.EXPR_FAMILIES[:] = self._saved["expr"]
        ca.BLOCK_FAMILIES[:] = self._saved["block"]
        sch.SCHEMAS[:] = self._saved["schema"]
        return False


def ablate_and_reinvent(family_id: str) -> dict[str, Any]:
    """CENTRAL HONESTY EXPERIMENT. Withhold a hand law, then test whether induction reinvents a
    structurally-equivalent law from the verified solutions that law once produced and re-solves the
    target task through the isolated verifier. Reports pass/fail with the reason — no rounding up.

    The library and induced store are isolated throughout so the ablation is CLEAN: after the hand law
    is removed, the only paths left to the target are the (ablated) hand law or the induced schema —
    never a cached recall. That is what makes ``hand_abstains_when_ablated`` an honest necessity check."""
    import tempfile
    from packages.code_reason.benchmarks.mastery_v1 import all_tasks
    spec = _ABLATION_FAMILIES[family_id]
    by_name = {t.name: t for t in all_tasks()}
    source_tasks = [by_name[n] for n in spec["sources"] if n in by_name]

    global INDUCED_STORE
    saved_lib, saved_store = ca.LIBRARY, INDUCED_STORE
    try:
        # WAKE (hand engine intact, isolated library): collect the verified solutions this family made.
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="wake_")) / "l.jsonl"
        templates = []
        for t in source_tasks:
            a = ca.author(t)
            if a.verified and a.body:
                templates.append(ca._normalize(a.body, ca._params(t.signature)))
        if len(templates) < 2:
            return {"family": family_id, "reinvented": False,
                    "reason": f"corpus insufficient: only {len(templates)} verified sibling solution(s) "
                              f"-- anti-unification needs >= 2", "n_sources": len(templates)}
        schema = anti_unify(templates, family=family_id, intents=[t.docstring for t in source_tasks],
                            arity=len(ca._params(source_tasks[0].signature)))
        if schema is None:
            return {"family": family_id, "reinvented": False,
                    "reason": "no clean schema: sources diverge at statement structure (v1 invents "
                              "expression-level holes only)", "n_sources": len(templates)}

        target = by_name[spec["target"]]
        holdout = spec["holdout"]() if spec["holdout"] else None
        # CHECK phase: fresh empty library + empty induced store, hand law(s) ablated.
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="check_")) / "l.jsonl"
        INDUCED_STORE = Path(tempfile.mkdtemp(prefix="noind_")) / "none.jsonl"      # nonexistent -> empty
        with _Ablation(spec["disable"]):
            hand_abstains = ca.author(target).body is None                          # the law was necessary
            reinvented_body = _solve_via(schema, target, ca._params(target.signature))
            generalized = _solve_via_full(schema, holdout) if holdout else None
    finally:
        ca.LIBRARY, INDUCED_STORE = saved_lib, saved_store

    reinvented = bool(hand_abstains and reinvented_body is not None)
    return {"family": family_id, "reinvented": reinvented, "hand_abstains_when_ablated": hand_abstains,
            "target": spec["target"], "mdl_gain": round(schema.mdl_gain(), 2), "n_holes": schema.n_holes,
            "generalized_to_novel_probe": generalized, "n_sources": len(templates),
            "skeleton": schema.skeleton_src,
            "reason": "reinvented and re-solved target via isolated verifier" if reinvented
                      else ("schema formed but did not re-solve target under ablation"
                            if hand_abstains else "hand did not abstain under ablation (not isolated)")}


def dp1d_reinvention_after_growth() -> dict[str, Any]:
    """I3b — FRONTIER 2's headline. v1 could not reinvent DP-1D: the corpus held a single sibling
    (coin_change), so anti-unification had nothing to generalize ('corpus insufficient'). Wake-sleep now
    GROWS a second genuine DP-1D exemplar (ordered change-counting, a near-variant that pins different
    holes of the same linear-DP scaffold). We author both siblings, anti-unify, ablate the hand dp1d
    schema, and test whether induction reinvents the DP-1D law from the grown pair and re-solves
    coin_change through the isolated verifier. Honest pass/fail — the corpus is grown, the gate is not
    weakened."""
    import tempfile
    from packages.code_reason.benchmarks.mastery_v1 import all_tasks
    by = {t.name: t for t in all_tasks()}
    coin, ways = by["coin_change"], _count_change_ways_task()
    global INDUCED_STORE
    saved_lib, saved_store = ca.LIBRARY, INDUCED_STORE
    try:
        # WAKE (hand engine intact, isolated library): author both DP-1D siblings -> verified bodies.
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="dp1d_wake_")) / "l.jsonl"
        templates: list[str] = []
        for t in (coin, ways):
            a = ca.author(t)
            if a.verified and a.body:
                templates.append(ca._normalize(a.body, ca._params(t.signature)))
        distinct = len(set(templates))
        if distinct < 2:
            return {"family": "dp1d", "reinvented": False, "n_sources": len(templates),
                    "reason": f"corpus growth produced only {distinct} DISTINCT DP-1D exemplar(s) "
                              f"-- anti-unification needs >= 2 that differ"}
        schema = anti_unify(templates, family="dp1d", intents=[coin.docstring, ways.docstring], arity=2)
        if schema is None:
            return {"family": "dp1d", "reinvented": False, "n_sources": len(templates),
                    "reason": "the grown DP-1D pair did not anti-unify to a clean law"}
        # CHECK: fresh empty library + empty induced store, hand dp1d ablated -> only induction can solve.
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="dp1d_check_")) / "l.jsonl"
        INDUCED_STORE = Path(tempfile.mkdtemp(prefix="dp1d_noind_")) / "none.jsonl"
        with _Ablation([("schema", "dp1d")]):
            hand_abstains = ca.author(coin).body is None
            reinvented_body = _solve_via(schema, coin, ca._params(coin.signature))
    finally:
        ca.LIBRARY, INDUCED_STORE = saved_lib, saved_store
    reinvented = bool(hand_abstains and reinvented_body is not None)
    return {"family": "dp1d", "reinvented": reinvented, "hand_abstains_when_ablated": hand_abstains,
            "target": "coin_change", "mdl_gain": round(schema.mdl_gain(), 2), "n_holes": schema.n_holes,
            "n_sources": len(templates), "skeleton": schema.skeleton_src,
            "reason": "reinvented DP-1D from the grown 2-exemplar family and re-solved coin_change via the "
                      "isolated verifier" if reinvented
                      else ("schema formed but did not re-solve coin_change under ablation" if hand_abstains
                            else "hand did not abstain under ablation (not isolated)")}


# ============================================================================ I5 — STATEMENT-LEVEL

def _statement_level_cases() -> list[tuple[str, Task, Task, Task]]:
    """Task triples whose members differ by exactly ONE loop-body statement (a bare fold/collect vs the
    same under a guard). Each is loop-only (no expression or composition shortcut), so the engine
    authors a multi-statement body and the pair's ONLY divergence is a whole statement. The third is a
    NOVEL task reachable only by generalizing that statement hole with a guard none of the sources used."""
    prod_all = Task("prod_all", "def prod_all(xs):", "Return the product of all numbers in xs.",
                    "assert prod_all([1, 2, 3, 4]) == 24\nassert prod_all([5]) == 5\n"
                    "assert prod_all([]) == 1\nassert prod_all([2, 3]) == 6",
                    reference="p = 1\nfor x in xs:\n    p = p * x\nreturn p",
                    hidden="assert prod_all([2, 2, 2]) == 8\nassert prod_all([-1, 4]) == -4")
    prod_pos = Task("prod_pos", "def prod_pos(xs):", "Return the product of the positive numbers in xs.",
                    "assert prod_pos([1, 2, -3, 4]) == 8\nassert prod_pos([-1, -2]) == 1\n"
                    "assert prod_pos([2, 3]) == 6\nassert prod_pos([]) == 1",
                    reference="p = 1\nfor x in xs:\n    if x > 0:\n        p = p * x\nreturn p",
                    hidden="assert prod_pos([5, -5, 2]) == 10")
    prod_even = Task("prod_even", "def prod_even(xs):", "Return the product of the even numbers in xs.",
                     "assert prod_even([1, 2, 3, 4]) == 8\nassert prod_even([1, 3, 5]) == 1\n"
                     "assert prod_even([2, 4]) == 8",
                     reference="p = 1\nfor x in xs:\n    if x % 2 == 0:\n        p = p * x\nreturn p",
                     hidden="assert prod_even([6, 7]) == 6")
    keep_all = Task("keep_all", "def keep_all(xs):", "Return a list copy holding every element of xs in order.",
                    "assert keep_all([3, -1, 2, -1]) == [3, -1, 2, -1]\nassert keep_all([]) == []\n"
                    "assert keep_all([5]) == [5]",
                    reference="o = []\nfor x in xs:\n    o.append(x)\nreturn o",
                    hidden="assert keep_all([7, 7]) == [7, 7]")
    keep_neg = Task("keep_neg", "def keep_neg(xs):", "Return the negative numbers of xs keeping order.",
                    "assert keep_neg([1, -2, 3, -4]) == [-2, -4]\nassert keep_neg([1, 2]) == []\n"
                    "assert keep_neg([-5]) == [-5]",
                    reference="o = []\nfor x in xs:\n    if x < 0:\n        o.append(x)\nreturn o",
                    hidden="assert keep_neg([-1, -2, 3]) == [-1, -2]")
    keep_nz = Task("keep_nz", "def keep_nz(xs):", "Return the nonzero numbers of xs keeping order.",
                   "assert keep_nz([0, 1, 0, 2]) == [1, 2]\nassert keep_nz([0, 0]) == []\n"
                   "assert keep_nz([3]) == [3]",
                   reference="o = []\nfor x in xs:\n    if x != 0:\n        o.append(x)\nreturn o",
                   hidden="assert keep_nz([0, 5, 0]) == [5]")
    return [("product-fold", prod_all, prod_pos, prod_even),
            ("guarded-collect", keep_all, keep_neg, keep_nz)]


def statement_level_probe() -> list[dict[str, Any]]:
    """I5. For each pair whose only difference is one statement: verify the engine (a) authors both as
    LOOP bodies, (b) anti-unifies them into ONE schema with a STATEMENT hole, and (c) re-solves BOTH
    sources AND a novel third through that schema via the isolated verifier. Per-case PASS/FAIL, honest."""
    import tempfile
    out: list[dict[str, Any]] = []
    saved_lib = ca.LIBRARY
    try:
        for name, ta, tb, tc in _statement_level_cases():
            ca.LIBRARY = Path(tempfile.mkdtemp(prefix=f"stmt_{name}_")) / "l.jsonl"
            aa, ab = ca.author(ta), ca.author(tb)
            loops = bool(aa.verified and ab.verified
                         and "for " in (aa.body or "") and "for " in (ab.body or ""))
            schema = None
            if loops:
                t1 = ca._normalize(aa.body, ca._params(ta.signature))
                t2 = ca._normalize(ab.body, ca._params(tb.signature))
                schema = anti_unify([t1, t2], family=name, intents=[ta.docstring, tb.docstring], arity=1)
            stmt_hole = bool(schema and _SHOLE_RE.search(schema.skeleton_src))
            sa = bool(schema and _solve_via(schema, ta, ca._params(ta.signature)))
            sb = bool(schema and _solve_via(schema, tb, ca._params(tb.signature)))
            sc = bool(schema and _solve_via(schema, tc, ca._params(tc.signature)))
            passed = bool(schema and stmt_hole and schema.n_holes == 1 and sa and sb and sc)
            out.append({"case": name, "passed": passed, "statement_hole": stmt_hole,
                        "n_holes": schema.n_holes if schema else None,
                        "authored_loops": loops, "solved_A": sa, "solved_B": sb,
                        "solved_novel_third": sc, "novel_third": tc.name,
                        "skeleton": schema.skeleton_src if schema else None})
    finally:
        ca.LIBRARY = saved_lib
    return out


# ============================================================================ report entrypoint

def _report() -> str:
    import tempfile
    import time
    from dataclasses import replace
    from packages.code_reason.benchmarks.mastery_v1 import all_tasks
    global INDUCED_STORE
    lines: list[str] = []
    t0 = time.time()
    # Side-effect-free: the whole report runs against isolated temp state, restored on exit, so the
    # real library and induced store are never written by measuring.
    saved_store, saved_lib = INDUCED_STORE, ca.LIBRARY
    ca.LIBRARY = Path(tempfile.mkdtemp(prefix="report_")) / "l.jsonl"
    try:
        # I1: re-discover a simple hand family from >= 3 solutions (the aggregate family).
        by = {t.name: t for t in all_tasks()}
        agg_tasks = [by[n] for n in ("total", "maximum", "minimum")]
        agg_tmpls = [ca._normalize(ca.author(t).body, ca._params(t.signature)) for t in agg_tasks]
        agg = anti_unify(agg_tmpls, family="aggregate", intents=[t.docstring for t in agg_tasks], arity=1)
        lines.append(f"I1 re-discovery: aggregate from 3 solutions -> skeleton '{agg.skeleton_src}' "
                     f"hole0={sorted(set(agg.holes[0]))}")

        # I3 (headline): per-family reinvention.
        i3 = {fam: ablate_and_reinvent(fam) for fam in _ABLATION_FAMILIES}
        for fam, r in i3.items():
            tag = "PASS" if r["reinvented"] else "----"
            lines.append(f"I3 {fam:<11} {tag}  {r['reason']}")

        # I3b (FRONTIER 2 headline): DP-1D reinvention AFTER wake-sleep grows a 2nd exemplar.
        r3b = dp1d_reinvention_after_growth()
        lines.append(f"I3b dp1d-grown {'PASS' if r3b['reinvented'] else '----'}  {r3b['reason']} "
                     f"(sources={r3b['n_sources']}, holes={r3b.get('n_holes')}, gain={r3b.get('mdl_gain')})")

        # I5 (FRONTIER 1 headline): statement-level anti-unification, per case.
        for c in statement_level_probe():
            lines.append(f"I5 {c['case']:<16} {'PASS' if c['passed'] else 'FAIL'}  stmt-hole={c['statement_hole']} "
                         f"solves A/B/novel={c['solved_A']}/{c['solved_B']}/{c['solved_novel_third']}")

        # I2 + I4 on a freshly-induced, WAKE-SLEEP GROWN store (rounds=2).
        empty = Path(tempfile.mkdtemp(prefix="empty_")) / "none.jsonl"      # nonexistent -> induction off
        INDUCED_STORE = Path(tempfile.mkdtemp(prefix="induced_")) / "induced.jsonl"
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="lib_")) / "library.jsonl"
        sleep = induce_and_promote(wake=True, rounds=2)

        # I2: an induced schema solves a task NO hand schema reaches (edit-distance variant whose
        # wording misses the hand dp2d keyword cue). Fresh library each call so nothing is recalled.
        probe = _min_edits_probe()
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="l2_")) / "l.jsonl"
        INDUCED_STORE, live = empty, INDUCED_STORE
        hand_res = ca.author(probe)                                          # induction OFF
        INDUCED_STORE = live
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="l3_")) / "l.jsonl"
        ind_res = ca.author(probe)                                           # induction ON
        lines.append(f"I2 induced-solves-new: sleep promoted {sleep['promoted']} schema(s); probe "
                     f"'{probe.name}' hand={hand_res.source} -> induced={ind_res.source} "
                     f"verified={ind_res.verified}")

        # I4: mastery_v2 — 12 novel held-out tasks; how many the induction engine reaches vs honest
        # abstain, fail MUST be 0. Fresh library so every solve is synthesis, not recall.
        ca.LIBRARY = Path(tempfile.mkdtemp(prefix="l4_")) / "l.jsonl"
        reached = abst = fail = 0
        reach_names = []
        for t in mastery_v2_tasks():
            a = ca.author(t)
            if not a.verified or not a.body:
                abst += 1
                continue
            full = t.test + ("\n" + t.hidden if t.hidden else "")
            if ca._run_candidate(replace(t, test=full), a.body).passed:
                reached += 1
                reach_names.append(f"{t.name}<-{a.source.replace('induced:', 'I:')[:14]}")
            else:
                fail += 1
        lines.append(f"I4 mastery_v2: reached {reached}/12  abstain {abst}  FAIL {fail}")
        lines.append(f"   reached-by: {reach_names}")
    finally:
        INDUCED_STORE, ca.LIBRARY = saved_store, saved_lib
    lines.append(f"runtime {round(time.time() - t0, 1)}s")
    return "\n".join(lines)


def mastery_v2_tasks() -> list[Task]:
    """12 NEW held-out tasks, none in mastery_v1 or the library, chosen to be BEYOND the hand schemas'
    cues (each hand-abstains) so the benchmark measures INDUCTION's added reach honestly. Some are
    cue-missing variants of a family with an induced law (reachable); the rest need genuinely new
    algorithms (honest abstain). Every task is well-posed (reference passes visible+hidden)."""
    return [
        # -- cue-missing DP-2D variants: hand dp2d cue ('distance'/'subsequence'/...) misses these --
        Task("transform_cost", "def transform_cost(a, b):",
             "Return the least number of single-letter inserts, removals, or swaps to rewrite a as b.",
             "assert transform_cost('cat', 'cut') == 1\nassert transform_cost('', 'ab') == 2\n"
             "assert transform_cost('abc', 'abc') == 0",
             reference=("m, n = len(a), len(b)\ndp = [[i + j for j in range(n + 1)] for i in range(m + 1)]\n"
                        "for i in range(1, m + 1):\n    for j in range(1, n + 1):\n"
                        "        dp[i][j] = dp[i-1][j-1] if a[i-1]==b[j-1] else 1+min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])\n"
                        "return dp[m][n]"),
             hidden="assert transform_cost('sunday', 'saturday') == 3\nassert transform_cost('a', '') == 1"),
        Task("shared_run", "def shared_run(p, q):",
             "Return how many characters p and q share in the same relative order.",
             "assert shared_run('abcde', 'ace') == 3\nassert shared_run('abc', 'abc') == 3\n"
             "assert shared_run('abc', 'xyz') == 0",
             reference=("m, n = len(p), len(q)\ndp = [[0]*(n+1) for _ in range(m+1)]\n"
                        "for i in range(1, m+1):\n    for j in range(1, n+1):\n"
                        "        dp[i][j] = dp[i-1][j-1]+1 if p[i-1]==q[j-1] else max(dp[i-1][j], dp[i][j-1])\n"
                        "return dp[m][n]"),
             hidden="assert shared_run('', 'x') == 0\nassert shared_run('aggtab', 'gxtxayb') == 4"),
        Task("similarity", "def similarity(u, v):",
             "Return the count of letters appearing in u and v in a consistent left-to-right pairing.",
             "assert similarity('abcde', 'ace') == 3\nassert similarity('xy', 'yx') == 1\n"
             "assert similarity('abc', 'abc') == 3",
             reference=("m, n = len(u), len(v)\ndp = [[0]*(n+1) for _ in range(m+1)]\n"
                        "for i in range(1, m+1):\n    for j in range(1, n+1):\n"
                        "        dp[i][j] = dp[i-1][j-1]+1 if u[i-1]==v[j-1] else max(dp[i-1][j], dp[i][j-1])\n"
                        "return dp[m][n]"),
             hidden="assert similarity('', '') == 0\nassert similarity('ab', 'ba') == 1"),
        Task("rewrite_ops", "def rewrite_ops(s, t):",
             "Return the smallest count of add, drop, or replace steps mapping string s onto string t.",
             "assert rewrite_ops('kitten', 'sitting') == 3\nassert rewrite_ops('abc', '') == 3\n"
             "assert rewrite_ops('x', 'x') == 0",
             reference=("m, n = len(s), len(t)\ndp = [[i + j for j in range(n + 1)] for i in range(m + 1)]\n"
                        "for i in range(1, m + 1):\n    for j in range(1, n + 1):\n"
                        "        dp[i][j] = dp[i-1][j-1] if s[i-1]==t[j-1] else 1+min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])\n"
                        "return dp[m][n]"),
             hidden="assert rewrite_ops('horse', 'ros') == 3\nassert rewrite_ops('', 'abc') == 3"),
        # -- genuinely beyond current laws (no induced sibling): honest ABSTAIN expected, fail stays 0.
        #    Each visible test is deliberately discriminating so a coincidental body cannot over-fit it.
        Task("gcd", "def gcd(a, b):", "Return the greatest common divisor of a and b.",
             "assert gcd(12, 8) == 4\nassert gcd(7, 5) == 1\nassert gcd(0, 5) == 5\nassert gcd(100, 60) == 20",
             reference="while b:\n    a, b = b, a % b\nreturn a", hidden="assert gcd(48, 36) == 12"),
        Task("is_prime", "def is_prime(n):", "Return True if n is a prime number.",
             "assert is_prime(2) is True\nassert is_prime(4) is False\nassert is_prime(17) is True\nassert is_prime(1) is False",
             reference=("if n < 2:\n    return False\nfor d in range(2, int(n**0.5) + 1):\n"
                        "    if n % d == 0:\n        return False\nreturn True"),
             hidden="assert is_prime(97) is True\nassert is_prime(100) is False"),
        Task("count_bits", "def count_bits(n):", "Return the number of 1 bits in the binary representation of n.",
             "assert count_bits(0) == 0\nassert count_bits(7) == 3\nassert count_bits(8) == 1\nassert count_bits(255) == 8",
             reference="return bin(n).count(chr(49))", hidden="assert count_bits(1023) == 10"),
        Task("reverse_words", "def reverse_words(s):", "Return s with the order of its space-separated words reversed.",
             "assert reverse_words('a b c') == 'c b a'\nassert reverse_words('hi') == 'hi'\n"
             "assert reverse_words('one two') == 'two one'",
             reference="return ' '.join(reversed(s.split()))", hidden="assert reverse_words('x y z w') == 'w z y x'"),
        Task("caesar", "def caesar(s, k):",
             "Return s with each lowercase letter advanced k places in the alphabet, wrapping.",
             "assert caesar('abc', 1) == 'bcd'\nassert caesar('xyz', 3) == 'abc'\nassert caesar('az', 2) == 'cb'",
             reference="return ''.join(chr((ord(c) - 97 + k) % 26 + 97) for c in s)",
             hidden="assert caesar('hello', 0) == 'hello'"),
        Task("collatz", "def collatz(n):", "Return the number of Collatz steps from n down to 1.",
             "assert collatz(1) == 0\nassert collatz(6) == 8\nassert collatz(2) == 1\nassert collatz(3) == 7",
             reference=("steps = 0\nwhile n != 1:\n    n = n // 2 if n % 2 == 0 else 3 * n + 1\n    steps += 1\nreturn steps"),
             hidden="assert collatz(7) == 16"),
        Task("primes_upto", "def primes_upto(n):", "Return the list of primes <= n in ascending order.",
             "assert primes_upto(10) == [2, 3, 5, 7]\nassert primes_upto(1) == []\nassert primes_upto(2) == [2]\n"
             "assert primes_upto(5) == [2, 3, 5]",
             reference=("out = []\nfor x in range(2, n + 1):\n    if all(x % d for d in range(2, int(x**0.5) + 1)):\n"
                        "        out.append(x)\nreturn out"),
             hidden="assert primes_upto(20) == [2, 3, 5, 7, 11, 13, 17, 19]"),
        Task("two_sum", "def two_sum(nums, target):",
             "Return True if two distinct positions in nums add to target.",
             "assert two_sum([2, 7, 11], 9) is True\nassert two_sum([1, 2, 3], 7) is False\n"
             "assert two_sum([2, 5], 7) is True\nassert two_sum([1, 1], 9) is False\nassert two_sum([3, 4], 6) is False",
             reference=("seen = set()\nfor x in nums:\n    if target - x in seen:\n        return True\n"
                        "    seen.add(x)\nreturn False"),
             hidden="assert two_sum([], 0) is False\nassert two_sum([4, 4], 8) is True"),
    ]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Delegate to the PACKAGE module instance: running as ``-m`` makes this file a separate ``__main__``
    # module, but code_author's induced-schema hook imports ``packages.code_reason.schema_induction``.
    # If _report ran here it would set INDUCED_STORE on the wrong copy and the hook would see none.
    from packages.code_reason import schema_induction as _pkg
    print(_pkg._report())
