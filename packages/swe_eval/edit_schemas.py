# -*- coding: utf-8 -*-
"""Edit schemas — the No-LLM PROPOSE step for repo-scale patches.

The wall the diagnostic mapped was patch generation: ``code_author`` synthesizes a function body
FROM SCRATCH by enumerating expression/​block skeletons, which cannot reproduce a large domain
function (astropy's ``_cstack``), and its FAIL_TO_PASS pytest node-ids parse to ZERO literal
examples. So from-scratch synthesis honestly abstains on real repo code.

But a repo FIX is almost never a from-scratch body — it is a small, structural EDIT to an existing
body. That is the same propose→verify shape ``code_author`` already lives by (AlphaGeometry: a cheap
generator + a perfect verifier), only the generator proposes MUTATIONS of the localized function
instead of whole bodies, and the verifier is the repo's own FAIL_TO_PASS/PASS_TO_PASS regression gate
(``regression_gate``), never a plausibility score. This is the "L3-induced edit schemas where they
match" lever: a finite family of domain-blind structural mutations, each VERIFIED, none shipped
unverified (fail-0).

Every family here is DOMAIN-BLIND (it carries no astropy/django knowledge): flip a comparison,
substitute an in-scope operand for a literal, delete a guarded block, toggle a boolean/return. These
are exactly the single-token/single-block edits that a large fraction of SWE-bench_Verified fixes are
(measured: 107/500 are single-file single-hunk with <=2 changed lines). The intelligence is the
enumerate-and-verify search + the crisp gate, not memorized answers — structure over memorization.

W-A WIDENING: the single-token/single-block cliff above is lifted by MULTI-TOKEN / MULTI-STATEMENT
families that stay just as domain-blind and just as enumerable, each candidate still whole-file and
still gated by the repo's own FAIL_TO_PASS/PASS_TO_PASS (never a plausibility score, never shipped
unverified):
  * ``none_guard_insertion``   — insert a missing ``if <param> is None: return/= <val>`` guard at the
                                 function head (the very common 'add the missing None/empty branch' fix).
  * ``guarded_early_return``   — a TWO-SITE coordinated edit: a guard that returns an alternative is
                                 inserted before an existing ``return`` (guard+return together).
  * ``condition_refinement``   — tighten/loosen an ``if`` test by AND/OR-ing a domain-blind predicate
                                 over an in-scope name (the missing-conjunct condition bug).
  * ``statement_wrap_guard``   — wrap an existing statement in ``if <cond>:`` (add a branch around it).
  * ``adjacent_stmt_swap``     — small multi-line block replacement: swap two adjacent simple
                                 statements (an ordering bug).
  * ``l3_induced``             — REUSE of the L3 induced edit schemas (``schema_induction``): when the
                                 localized function's arity matches an induced law, its verified fillings
                                 are offered as whole-body candidates. Inert when the induced store is
                                 empty (honest: it fires only where a learned schema actually matches).

This module PROPOSES only; it never decides a candidate is correct. It returns candidate PATCHED FILE
TEXTS (with a schema id + human description); the caller diffs them against the original and the
regression gate is the sole authority on which, if any, is green.
"""
from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass, field
from typing import Iterator

# a conservative cap so enumeration over a large function can never explode the verify budget
MAX_CANDIDATES_PER_FAMILY = 60
MAX_TOTAL_CANDIDATES = 240
# multi-edit families multiply (in-scope name x template), so they carry a TIGHTER per-family cap:
# the single-token families above are enumerated first (they never starve), and the regression gate's
# verify budget is the real wall-clock bound — this only keeps the proposed list itself bounded.
MAX_MULTI_PER_FAMILY = 40


@dataclass
class EditCandidate:
    schema: str                 # family id (operand_substitution | comparison_flip | ...)
    description: str            # human-readable, for the certificate
    new_source: str            # the WHOLE file text after this single structural edit
    anchor_line: int = 0       # 1-based line in the original where the edit is centred


# ── source-segment splice over AST node positions (robust, no regex on code) ──────────────────────

def _segment_span(src: str, node: ast.AST) -> tuple[int, int] | None:
    """Absolute [start, end) character offsets of ``node`` in ``src`` using its position attrs."""
    try:
        lines = src.splitlines(keepends=True)
        starts = [0]
        for ln in lines:
            starts.append(starts[-1] + len(ln))
        s = starts[node.lineno - 1] + node.col_offset
        e = starts[node.end_lineno - 1] + node.end_col_offset
        return s, e
    except Exception:
        return None


def _splice(src: str, node: ast.AST, new_text: str) -> str | None:
    span = _segment_span(src, node)
    if span is None:
        return None
    s, e = span
    return src[:s] + new_text + src[e:]


def _target_function(src: str, fn_name: str, hint_line: int = 0):
    """Find the FunctionDef named ``fn_name`` in ``src`` (nearest to ``hint_line`` if several)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None, None
    cands = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name]
    if not cands:
        return tree, None
    if hint_line and len(cands) > 1:
        cands.sort(key=lambda n: abs(n.lineno - hint_line))
    return tree, cands[0]


def _in_scope_names(fn: ast.AST) -> list[str]:
    """Parameter names + names assigned anywhere in the function — the operands an edit may
    substitute in (domain-blind: only names the function itself introduces)."""
    names: list[str] = []
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = fn.args
        for arg in list(a.args) + list(a.kwonlyargs) + list(a.posonlyargs):
            names.append(arg.arg)
        if a.vararg:
            names.append(a.vararg.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
        elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(getattr(node, "target", None), ast.Name):
            names.append(node.target.id)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen and not n.startswith("_"):
            seen.add(n)
            out.append(n)
    return out


# ── the domain-blind edit-schema families (each yields whole patched file texts) ──────────────────

_CMP_FLIP = {ast.Lt: "<=", ast.LtE: "<", ast.Gt: ">=", ast.GtE: ">", ast.Eq: "!=", ast.NotEq: "=="}
_CMP_SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}


def _family_operand_substitution(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """`X = <literal>` or `X = <name>`  ->  substitute each OTHER in-scope name for the RHS.
    Reaches real fixes where an assignment used the wrong operand (e.g. astropy-12907:
    ``cright[...] = 1`` should be ``= right``)."""
    scope = _in_scope_names(fn)
    n = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        val = node.value
        if not isinstance(val, (ast.Constant, ast.Name)):
            continue
        cur = val.id if isinstance(val, ast.Name) else None
        for name in scope:
            if name == cur or n >= MAX_CANDIDATES_PER_FAMILY:
                continue
            new = _splice(src, val, name)
            if new is None or new == src:
                continue
            try:
                ast.parse(new)
            except SyntaxError:
                continue
            n += 1
            yield EditCandidate("operand_substitution",
                                f"substitute in-scope name '{name}' for the assigned RHS at line {val.lineno}",
                                new, val.lineno)


def _family_comparison_flip(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """Flip a single comparison operator (< <-> <=, > <-> >=, == <-> !=) — boundary/off-by-one bugs."""
    n = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        op = type(node.ops[0])
        if op not in _CMP_FLIP or n >= MAX_CANDIDATES_PER_FAMILY:
            continue
        left, right = node.left, node.comparators[0]
        lseg, rseg = _segment_span(src, left), _segment_span(src, right)
        cspan = _segment_span(src, node)
        if not (lseg and rseg and cspan):
            continue
        new_cmp = src[lseg[0]:lseg[1]] + f" {_CMP_FLIP[op]} " + src[rseg[0]:rseg[1]]
        new = src[:cspan[0]] + new_cmp + src[cspan[1]:]
        if new == src:
            continue
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        n += 1
        yield EditCandidate("comparison_flip",
                            f"flip comparison {_CMP_SYMBOL[op]} -> {_CMP_FLIP[op]} at line {node.lineno}",
                            new, node.lineno)


def _family_boolop_flip(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """`a and b` <-> `a or b` — the classic wrong-connective condition bug."""
    n = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.BoolOp) or n >= MAX_CANDIDATES_PER_FAMILY:
            continue
        span = _segment_span(src, node)
        if not span:
            continue
        seg = src[span[0]:span[1]]
        if isinstance(node.op, ast.And) and " and " in seg:
            new_seg = seg.replace(" and ", " or ", 1)
        elif isinstance(node.op, ast.Or) and " or " in seg:
            new_seg = seg.replace(" or ", " and ", 1)
        else:
            continue
        new = src[:span[0]] + new_seg + src[span[1]:]
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        n += 1
        yield EditCandidate("boolop_flip", f"flip boolean connective at line {node.lineno}", new,
                            node.lineno)


def _family_block_deletion(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """Delete a single top-level statement of the function body (esp. an `if`-guard). Reaches fixes
    where a spurious block must be removed (e.g. astropy-13236 deletes an ndarray-view guard)."""
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    body = fn.body
    lines = src.splitlines(keepends=True)
    n = 0
    for stmt in body:
        if isinstance(stmt, (ast.Return, ast.Raise)) or n >= MAX_CANDIDATES_PER_FAMILY:
            continue                      # never delete the sole return/raise skeleton blindly
        s, e = stmt.lineno - 1, stmt.end_lineno
        new = "".join(lines[:s] + lines[e:])
        if new == src:
            continue
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        n += 1
        head = (lines[s].strip()[:50] if s < len(lines) else "")
        yield EditCandidate("block_deletion",
                            f"delete statement block (lines {stmt.lineno}-{stmt.end_lineno}: {head})",
                            new, stmt.lineno)


def _family_return_toggle(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """`return True` <-> `return False` — an inverted predicate."""
    n = 0
    for node in ast.walk(fn):
        if (isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, bool) and n < MAX_CANDIDATES_PER_FAMILY):
            new = _splice(src, node.value, str(not node.value.value))
            if new and new != src:
                n += 1
                yield EditCandidate("return_toggle",
                                    f"toggle boolean return at line {node.lineno}", new, node.lineno)


def _family_unary_not_toggle(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """Add/remove a `not` on an `if` test — an inverted guard."""
    n = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or n >= MAX_CANDIDATES_PER_FAMILY:
            continue
        test = node.test
        span = _segment_span(src, test)
        if not span:
            continue
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = _segment_span(src, test.operand)
            if not inner:
                continue
            new_seg = src[inner[0]:inner[1]]
        else:
            new_seg = f"not ({src[span[0]:span[1]]})"
        new = src[:span[0]] + new_seg + src[span[1]:]
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        n += 1
        yield EditCandidate("unary_not_toggle", f"toggle `not` on the if-test at line {node.lineno}",
                            new, node.lineno)


# ── MULTI-TOKEN / MULTI-STATEMENT families (W-A widening; each still bounded + verified) ──────────

def _body_statements(fn: ast.AST) -> list[ast.stmt]:
    return list(fn.body) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) else []


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _insert_lines_before(src: str, stmt: ast.stmt, block_lines: list[str]) -> str | None:
    """Splice a block (already correctly indented, no trailing newline needed per line) BEFORE the line
    where ``stmt`` starts, matching that statement's own indentation. Whole-file text out (or None)."""
    lines = src.splitlines(keepends=True)
    s = stmt.lineno - 1
    if s < 0 or s >= len(lines):
        return None
    indent = _indent_of(lines[s])
    block = "".join(f"{indent}{bl}\n" for bl in block_lines)
    return "".join(lines[:s]) + block + "".join(lines[s:])


def _wrap_statement_in_guard(src: str, stmt: ast.stmt, cond: str) -> str | None:
    """Replace statement lines [start,end) with ``if <cond>:`` + the same statement indented one level
    deeper (adds a branch AROUND an existing statement). Whole-file text out (or None)."""
    lines = src.splitlines(keepends=True)
    s, e = stmt.lineno - 1, stmt.end_lineno
    if s < 0 or e > len(lines):
        return None
    indent = _indent_of(lines[s])
    guard = f"{indent}if {cond}:\n"
    inner = "".join(("    " + ln) if ln.strip() else ln for ln in lines[s:e])
    return "".join(lines[:s]) + guard + inner + "".join(lines[e:])


def _guard_predicates(scope: list[str]) -> list[str]:
    """Domain-blind boolean predicates over in-scope NAMES — the only conditions an inserted guard or a
    refined condition may use (no literal domain knowledge, only names the function itself introduces)."""
    preds: list[str] = []
    for name in scope:
        preds.append(f"{name} is None")
        preds.append(f"{name} is not None")
        preds.append(f"not {name}")
        preds.append(f"{name}")
    return preds


def _guard_values(scope: list[str]) -> list[str]:
    """Domain-blind return/assign values an inserted guard may use: None, the empty containers, and any
    in-scope name (so a guard can early-return an already-computed value)."""
    return ["None", "[]", "{}", "''", "0"] + list(scope)


def _family_none_guard_insertion(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """STATEMENT INSERTION: add a missing ``if <param> is None:`` branch at the function head — either an
    early ``return <val>`` or a default ``<param> = <val>``. Reaches the extremely common repo fix that
    adds a None/empty guard on an argument (a multi-line, two-token coordinated edit)."""
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    body = _body_statements(fn)
    if not body:
        return
    params = [a.arg for a in list(fn.args.args) + list(fn.args.kwonlyargs) + list(fn.args.posonlyargs)]
    params = [p for p in params if p not in ("self", "cls")]
    first = body[0]
    scope = _in_scope_names(fn)
    n = 0
    for p in params:
        for val in ["None", "[]", "{}"] + [q for q in params if q != p]:
            if n >= MAX_MULTI_PER_FAMILY:
                return
            new = _insert_lines_before(src, first, [f"if {p} is None:", f"    return {val}"])
            if new and new != src:
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
                n += 1
                yield EditCandidate("none_guard_insertion",
                                    f"insert missing guard `if {p} is None: return {val}` at the function head",
                                    new, first.lineno)
        for val in _guard_values(scope):
            if n >= MAX_MULTI_PER_FAMILY:
                return
            if val == p:
                continue
            new = _insert_lines_before(src, first, [f"if {p} is None:", f"    {p} = {val}"])
            if new and new != src:
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
                n += 1
                yield EditCandidate("none_guard_insertion",
                                    f"insert missing default `if {p} is None: {p} = {val}` at the function head",
                                    new, first.lineno)


def _family_guarded_early_return(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """TWO-SITE coordinated edit (guard + return): before an existing ``return`` statement, insert a
    guard that returns an ALTERNATIVE value for a domain-blind condition — the classic 'handle this case
    before the normal return' fix, expressed as two coordinated lines."""
    scope = _in_scope_names(fn)
    preds = _guard_predicates(scope)
    vals = _guard_values(scope)
    n = 0
    for stmt in ast.walk(fn):
        if not isinstance(stmt, ast.Return):
            continue
        # value-major (breadth-first over conditions): so every CONDITION kind is reachable within the
        # per-family cap for the common early-return values, not starved by an earlier condition's values.
        for val in vals:
            for cond in preds:
                if n >= MAX_MULTI_PER_FAMILY:
                    return
                new = _insert_lines_before(src, stmt, [f"if {cond}:", f"    return {val}"])
                if new is None or new == src:
                    continue
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
                n += 1
                yield EditCandidate("guarded_early_return",
                                    f"insert guard `if {cond}: return {val}` before the return at line {stmt.lineno}",
                                    new, stmt.lineno)


def _family_condition_refinement(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """CONDITION REFINEMENT: tighten (AND) or loosen (OR) an existing ``if`` test with a domain-blind
    predicate over an in-scope name — the missing-conjunct / extra-disjunct condition bug (multi-token,
    single edit site)."""
    scope = _in_scope_names(fn)
    n = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        span = _segment_span(src, node.test)
        if not span:
            continue
        cur = src[span[0]:span[1]]
        for name in scope:
            for extra, joiner in ((f"{name} is not None", "and"), (f"{name} is None", "or"),
                                  (f"not {name}", "and"), (f"{name}", "and")):
                if n >= MAX_MULTI_PER_FAMILY:
                    return
                new_test = f"({cur}) {joiner} {extra}"
                new = src[:span[0]] + new_test + src[span[1]:]
                if new == src:
                    continue
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
                n += 1
                yield EditCandidate("condition_refinement",
                                    f"refine the if-test at line {node.lineno}: ... {joiner} {extra}",
                                    new, node.lineno)


def _family_statement_wrap_guard(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """STATEMENT INSERTION (branch): wrap a single top-level body statement in ``if <cond>:`` so it runs
    only under a domain-blind condition — reaches the 'this line should be conditional' fix."""
    body = _body_statements(fn)
    scope = _in_scope_names(fn)
    preds = _guard_predicates(scope)
    n = 0
    for stmt in body:
        if isinstance(stmt, (ast.Return, ast.Raise, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for cond in preds:
            if n >= MAX_MULTI_PER_FAMILY:
                return
            new = _wrap_statement_in_guard(src, stmt, cond)
            if new is None or new == src:
                continue
            try:
                ast.parse(new)
            except SyntaxError:
                continue
            n += 1
            head = src.splitlines()[stmt.lineno - 1].strip()[:40]
            yield EditCandidate("statement_wrap_guard",
                                f"wrap statement at line {stmt.lineno} ({head}) in `if {cond}:`",
                                new, stmt.lineno)


def _family_adjacent_stmt_swap(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """SMALL MULTI-LINE BLOCK REPLACEMENT: swap two ADJACENT simple statements (assignment/expr/aug) at
    the same body level — an ordering bug. Only fires when the two statements are literally adjacent in
    the source (no interleaved comment/blank), so the swap is a clean, reversible block replacement."""
    body = _body_statements(fn)
    lines = src.splitlines(keepends=True)
    simple = (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr)
    n = 0
    for a, b in zip(body, body[1:]):
        if n >= MAX_MULTI_PER_FAMILY:
            return
        if not (isinstance(a, simple) and isinstance(b, simple)):
            continue
        a0, a1 = a.lineno - 1, a.end_lineno
        b0, b1 = b.lineno - 1, b.end_lineno
        if a1 != b0:                       # require exact adjacency (no comment/blank between)
            continue
        if _indent_of(lines[a0]) != _indent_of(lines[b0]):
            continue
        new = ("".join(lines[:a0]) + "".join(lines[b0:b1]) + "".join(lines[a0:a1])
               + "".join(lines[b1:]))
        if new == src:
            continue
        try:
            ast.parse(new)
        except SyntaxError:
            continue
        n += 1
        yield EditCandidate("adjacent_stmt_swap",
                            f"swap adjacent statements at lines {a.lineno} and {b.lineno}",
                            new, a.lineno)


def _family_l3_induced(src: str, fn: ast.AST) -> Iterator[EditCandidate]:
    """L3 REUSE: consult the induced edit schemas (``schema_induction.induced_candidates``) — a learned,
    verification-gated family — and offer each filling whose arity matches the localized function as a
    WHOLE-BODY replacement candidate. Inert (yields nothing) when the induced store is empty, so this
    never fabricates: it fires only where a genuinely learned schema matches the function's shape."""
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return
    params = [a.arg for a in list(fn.args.posonlyargs) + list(fn.args.args)]
    try:
        from packages.code_reason import schema_induction as si
        from packages.code_reason import code_author as ca
    except Exception:
        return
    try:
        specs = si.load_induced() + (si.load_grown() if getattr(si, "LOAD_GROWN", False) else [])
    except Exception:
        specs = []
    if not specs or not params:
        return
    # find the target function node span to replace its whole body
    span = _segment_span(src, fn)
    if span is None:
        return
    import textwrap
    lines = src.splitlines(keepends=True)
    n = 0
    try:
        for family, body in si.induced_candidates(params, "", budget=MAX_MULTI_PER_FAMILY):
            if n >= MAX_MULTI_PER_FAMILY:
                return
            # build the full function text: original signature line + the induced body, indented
            sig_line = lines[fn.lineno - 1].rstrip("\n")
            base_indent = _indent_of(sig_line)
            new_fn = sig_line + "\n" + textwrap.indent(
                textwrap.dedent(body).strip(), base_indent + "    ") + "\n"
            new = src[:span[0]] + new_fn.strip("\n") + src[span[1]:]
            if new == src:
                continue
            try:
                ast.parse(new)
            except SyntaxError:
                continue
            n += 1
            yield EditCandidate("l3_induced",
                                f"L3 induced schema '{family}' whole-body fill for {fn.name}",
                                new, fn.lineno)
    except Exception:
        return


_FAMILIES = [
    _family_operand_substitution,   # reaches wrong-operand assignments (12907)
    _family_comparison_flip,        # boundary bugs
    _family_boolop_flip,            # wrong connective
    _family_block_deletion,         # spurious block (13236)
    _family_return_toggle,          # inverted predicate
    _family_unary_not_toggle,       # inverted guard
    # ── multi-token / multi-statement (W-A widening), tried after the cheap single-token ones ──
    _family_none_guard_insertion,   # add a missing None/empty guard branch (statement insertion)
    _family_guarded_early_return,   # guard + return coordinated (two-site)
    _family_condition_refinement,   # missing-conjunct condition bug (multi-token)
    _family_statement_wrap_guard,   # wrap a statement in a branch (statement insertion)
    _family_adjacent_stmt_swap,     # small multi-line block replacement (ordering)
    _family_l3_induced,             # reuse L3 induced edit schemas where they match (inert if none)
]


def propose_edits(file_source: str, fn_name: str, hint_line: int = 0) -> list[EditCandidate]:
    """Enumerate every domain-blind structural edit of the target function, cheapest family first.
    Deterministic order (so a run is reproducible); de-duplicated by resulting source."""
    tree, fn = _target_function(file_source, fn_name, hint_line)
    if fn is None:
        return []
    out: list[EditCandidate] = []
    seen: set[str] = set()
    for fam in _FAMILIES:
        for cand in fam(file_source, fn):
            if len(out) >= MAX_TOTAL_CANDIDATES:
                return out
            if cand.new_source in seen:
                continue
            seen.add(cand.new_source)
            out.append(cand)
    return out


def unified_diff(original: str, patched: str, repo_path: str) -> str:
    """A git-applyable unified diff (a/<path> b/<path>) between two file texts."""
    a = original.splitlines(keepends=True)
    b = patched.splitlines(keepends=True)
    if a and not a[-1].endswith("\n"):
        a[-1] += "\n"
    if b and not b[-1].endswith("\n"):
        b[-1] += "\n"
    diff = difflib.unified_diff(a, b, fromfile=f"a/{repo_path}", tofile=f"b/{repo_path}")
    return "".join(diff)


def combine_diffs(diffs: list[str]) -> str:
    """Concatenate several single-file git-shaped diffs into ONE multi-file patch (git apply reads the
    per-file ``--- a/… / +++ b/…`` sections independently). This is the whole multi-file mechanism: a
    candidate spanning two files is just the two files' edits applied together and gated as one — the
    regression gate remains the sole authority (fail-0 unchanged)."""
    return "".join(d for d in diffs if d and d.strip())
