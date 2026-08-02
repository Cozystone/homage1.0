# -*- coding: utf-8 -*-
"""Code authorship — verification-anchored program synthesis, the doctrine's path to a code master.

Owner (2026-07-21): make ATANOR a code master. The honest architecture is NOT LLM generation (that
is the memorization path we reject) and NOT a stub that abstains. It is what a No-LLM structural
mind can genuinely do and grow: SYNTHESIZE candidate programs from a finite, composable library of
code structures, then VERIFY every candidate against the task's own tests, and ship only what
passes. The mastery is not fluent typing — it is that ATANOR NEVER SHIPS UNVERIFIED CODE, and its
independent capability GROWS as verified solutions enter its library (a flywheel, like every other).

Four sources of candidates, tried cheapest / most-independent first:
  1. LIBRARY — a same-SHAPED task solved before, its body stored param-normalized so it re-fits any
     isomorphic signature (learned, near-instant). Persisted to data/code_reason/library.jsonl.
  2. SKELETONS — domain-blind program structures, split into EXPRESSION families (binary op, index,
     aggregate, string transform, list map/filter, numeric, membership, 3-arg order) and BLOCK
     families (fold-into-dict counters, bounded control loops). Classic enumerate-and-verify
     synthesis: the intelligence is the search + the hard test gate — "structure over memorization".
  3. COMPOSITION — 2-stage pipelines (expression A -> bound to a temp -> expression B), breadth-
     limited. This is where nontrivial tasks fall out (e.g. sort-of-the-squares) that no single
     family reaches, without adding any bespoke, task-specific skeleton.
  4. ADVISOR (optional) — for a task nothing above solves, a frontier model may DRAFT a body, but it
     is UNTRUSTED: verified only through the isolated subprocess gate and kept only if it passes
     (advisor drafts, ATANOR judges — the Brain-Link doctrine). Off by default.

Two-tier verification keeps it both fast and safe. The SEARCH runs each of our own generated
candidates in-process in a restricted namespace (microseconds), so exhausting the space on an
unsolvable task is cheap and it correctly ABSTAINS. Before anything is SHIPPED (or for any untrusted
advisor draft), the winner is re-certified by the original isolated-subprocess oracle. Nothing
unverified is ever returned — abstention over a wrong program is the no-fabrication floor for code.
"""
from __future__ import annotations

import ast
import builtins as _builtins
import json
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from packages.code_reason.authorship_harness import Task, _run_candidate
from packages.code_reason.algorithm_schemas import schema_candidates

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "data" / "code_reason" / "library.jsonl"

# breadth cap for the guided composition search (in-process, so this stays well under a second)
COMPOSE_BUDGET = 8000


def _params(signature: str) -> list[str]:
    """The parameter names from a 'def f(a, b):' signature."""
    m = re.search(r"def\s+\w+\s*\(([^)]*)\)", signature)
    if not m:
        return []
    return [p.strip().split(":")[0].split("=")[0].strip()
            for p in m.group(1).split(",") if p.strip()]


def _parse_examples(task: Task) -> tuple[tuple[tuple, Any], ...]:
    """Parse the visible test into literal (args, expected) pairs from ``assert f(...) == literal``.
    Content-learning schemas (VALUE-MAP) induce from these; the induced body is still verified."""
    m = re.search(r"def\s+(\w+)", task.signature)
    if not m:
        return ()
    fname = m.group(1)
    out: list[tuple[tuple, Any]] = []
    try:
        tree = ast.parse(task.test)
    except SyntaxError:
        return ()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
                and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)):
            left = node.test.left
            if isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == fname:
                try:
                    args = tuple(ast.literal_eval(a) for a in left.args)
                    expected = ast.literal_eval(node.test.comparators[0])
                    out.append((args, expected))
                except (ValueError, SyntaxError):
                    continue
    return tuple(out)


# ================================================================= expression skeleton families
# Each yields EXPRESSION strings (no 'return') over the given parameter names. Used directly
# (wrapped as 'return <expr>') AND as the stages of a composition. Domain-blind structures only.

def _fam_binary(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 2:
        a, b = params
        for op in ("+", "-", "*", "/", "//", "%", "**"):
            yield f"{a} {op} {b}"
        for cmp in ("==", "!=", "<", ">", "<=", ">="):
            yield f"{a} {cmp} {b}"
        yield f"{a} and {b}"
        yield f"{a} or {b}"
        yield f"max({a}, {b})"
        yield f"min({a}, {b})"


def _fam_numeric(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 1:
        n = params[0]
        for e in (f"abs({n})", f"-{n}", f"{n} * {n}", f"{n} ** 2",
                  f"{n} % 2 == 0", f"{n} % 2 != 0", f"{n} % 3 == 0",
                  f"{n} > 0", f"{n} < 0", f"{n} == 0",
                  f"sum(int(_d) for _d in str(abs({n})))",   # digit sum
                  f"len(str(abs({n})))"):                    # digit count
            yield e


def _fam_numeric2(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 2:
        a, b = params
        for e in (f"{a} % {b} == 0", f"{b} % {a} == 0",
                  f"abs({a} - {b})", f"({a} + {b}) / 2"):
            yield e


def _fam_index(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 1:
        xs = params[0]
        for e in (f"{xs}[0]", f"{xs}[-1]", f"{xs}[1]", f"{xs}[-2]", f"{xs}[len({xs}) // 2]"):
            yield e


def _fam_aggregate(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 1:
        xs = params[0]
        for e in (f"len({xs})", f"sum({xs})", f"min({xs})", f"max({xs})",
                  f"sorted({xs})", f"sorted({xs}, reverse=True)",
                  f"sorted(set({xs}))", f"list(reversed({xs}))",
                  f"list(dict.fromkeys({xs}))", f"sum({xs}) / len({xs})"):
            yield e


def _fam_string(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 1:
        s = params[0]
        for e in (f"{s}.upper()", f"{s}.lower()", f"{s}.strip()", f"{s}.title()",
                  f"{s}.capitalize()", f"{s}.swapcase()",
                  f"{s}[::-1]", f"{s} == {s}[::-1]",
                  f"''.join({s}.split())", f"' '.join({s}.split())"):
            yield e


def _fam_list_comp(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 1:
        xs = params[0]
        for e in (f"[_x * _x for _x in {xs}]", f"[_x * 2 for _x in {xs}]",
                  f"[-_x for _x in {xs}]", f"[abs(_x) for _x in {xs}]",
                  f"[_x for _x in {xs} if _x % 2 == 0]", f"[_x for _x in {xs} if _x % 2 != 0]",
                  f"[_x for _x in {xs} if _x > 0]", f"[str(_x) for _x in {xs}]"):
            yield e


def _fam_membership(params: list[str], intent: str) -> Iterator[str]:
    """count-of-a-charset patterns, seeded from a set named in the intent (e.g. 'aeiou')."""
    if len(params) == 1:
        s = params[0]
        sets = re.findall(r"\(([a-z]{2,})\)", intent.lower()) + ["aeiou"]
        seen: set[str] = set()
        for chars in sets:
            if chars in seen:
                continue
            seen.add(chars)
            yield f"sum(1 for _c in {s} if _c in '{chars}')"


def _fam_triple(params: list[str], intent: str) -> Iterator[str]:
    if len(params) == 3:
        a, b, c = params
        for e in (f"sorted([{a}, {b}, {c}])[1]",          # median-of-three (== clamp when lo<=hi)
                  f"max({b}, min({a}, {c}))", f"min({c}, max({a}, {b}))",
                  f"max({a}, {b}, {c})", f"min({a}, {b}, {c})",
                  f"{a} + {b} + {c}", f"({a} + {b} + {c}) / 3"):
            yield e


EXPR_FAMILIES: list[Callable[[list[str], str], Iterator[str]]] = [
    _fam_binary, _fam_numeric, _fam_numeric2, _fam_index, _fam_aggregate,
    _fam_string, _fam_list_comp, _fam_membership, _fam_triple,
]


# ================================================================= block skeleton families
# Full multi-line bodies (used directly, not in composition). Generic control/data structures only;
# every loop is bounded (iterates a finite input or a strictly-shrinking range) so in-process search
# can never hang.

def _blk_count_dict(params: list[str], intent: str) -> Iterator[str]:
    """Fold a sequence into a count dict, then read it in the common ways."""
    if len(params) == 1:
        xs = params[0]
        base = (f"counts = {{}}\n"
                f"for _k in {xs}:\n"
                f"    counts[_k] = counts.get(_k, 0) + 1\n")
        yield base + "return counts"                                  # frequency map
        yield base + "return max(counts, key=counts.get)"            # mode (most frequent)
        yield base + "return min(counts, key=counts.get)"            # least frequent
        yield base + "return max(counts.values())"                   # highest count
        yield base + "return len(counts)"                            # distinct count


def _blk_accumulate(params: list[str], intent: str) -> Iterator[str]:
    """Fold a sequence into a scalar accumulator: initialize, then update once per element, optionally
    under a guard. A domain-blind multi-statement BLOCK (no task-specific constant) that reaches folds
    no expression family or 2-stage composition produces — product, guarded sum, guarded count — and,
    because two of these differ by exactly one loop-body STATEMENT, the material L3 statement-level
    anti-unification abstracts into a single scaffold with a statement hole."""
    if len(params) != 1:
        return
    xs = params[0]
    guards = ["_x > 0", "_x < 0", "_x % 2 == 0", "_x % 2 != 0"]
    for init, op in (("1", "*"), ("0", "+")):
        yield f"_acc = {init}\nfor _x in {xs}:\n    _acc = _acc {op} _x\nreturn _acc"     # bare fold
        for g in guards:                                                                   # guarded fold
            yield f"_acc = {init}\nfor _x in {xs}:\n    if {g}:\n        _acc = _acc {op} _x\nreturn _acc"
    for g in guards:                                                                       # guarded count
        yield f"_acc = 0\nfor _x in {xs}:\n    if {g}:\n        _acc = _acc + 1\nreturn _acc"
    yield f"_out = []\nfor _x in {xs}:\n    _out.append(_x)\nreturn _out"                    # bare collect
    for g in guards:                                                                       # guarded collect
        yield f"_out = []\nfor _x in {xs}:\n    if {g}:\n        _out.append(_x)\nreturn _out"


def _blk_control(params: list[str], intent: str) -> Iterator[str]:
    """Bounded control-flow structures: accumulate over a range, or binary-search a sorted list."""
    if len(params) == 1:
        n = params[0]
        yield (f"_r = 1\nfor _i in range(2, {n} + 1):\n    _r *= _i\nreturn _r")           # factorial
        yield (f"_a, _b = 0, 1\nfor _i in range({n}):\n    _a, _b = _b, _a + _b\nreturn _a")  # fib(n)
    if len(params) == 2:
        xs, target = params
        yield (f"_lo, _hi = 0, len({xs}) - 1\n"
               f"while _lo <= _hi:\n"
               f"    _mid = (_lo + _hi) // 2\n"
               f"    if {xs}[_mid] == {target}:\n"
               f"        return _mid\n"
               f"    if {xs}[_mid] < {target}:\n"
               f"        _lo = _mid + 1\n"
               f"    else:\n"
               f"        _hi = _mid - 1\n"
               f"return -1")


BLOCK_FAMILIES: list[Callable[[list[str], str], Iterator[str]]] = [
    _blk_count_dict, _blk_control, _blk_accumulate,
]


# ================================================================= guided composition (depth <= 3)

def _split_asserts(test: str) -> list[str]:
    return [ln for ln in test.splitlines() if ln.strip().startswith("assert")]


def _partial_score(task: Task, body: str, asserts: list[str]) -> float:
    """Fraction of the visible asserts a (possibly partial, identity-completed) pipeline satisfies —
    the beam ranking signal for going one stage deeper."""
    if not asserts:
        return 0.0
    return sum(_exec_ok(task.signature, body, a) for a in asserts) / len(asserts)


def _library_expr_atoms(invar: str, limit: int = 40) -> Iterator[str]:
    """Single-expression library solutions, re-fit to one input var, offered as composition MACRO
    ATOMS — a learned transform becomes reusable as a pipeline stage."""
    n = 0
    for templates in _load_library().values():
        for t in templates:
            t = t.strip()
            if n >= limit:
                return
            if t.startswith("return ") and "\n" not in t and "_a1" not in t and "_a0" in t:
                n += 1
                yield t[len("return "):].replace("_a0", invar)


def _stage_exprs(invars: list[str], intent: str) -> Iterator[str]:
    """The transforms available at one composition stage: every expression family over the stage's
    inputs, plus library macro atoms when the stage carries a single value."""
    for fam in EXPR_FAMILIES:
        yield from fam(invars, intent)
    if len(invars) == 1:
        yield from _library_expr_atoms(invars[0])


def _compose_guided(task: Task, params: list[str], beam: int = 16,
                    max_depth: int = 3, budget: int = COMPOSE_BUDGET) -> Iterator[str]:
    """Type-chained pipelines exprA -> _t1 -> _t2 -> ... , each stage a single value fed to the next.
    Depth-2 is enumerated in full (cheap); depth-3 is beam-guided — only the depth-2 prefixes whose
    identity completion scores best on the visible examples are extended one more stage. Reaches
    tasks no single family reaches, without any task-specific skeleton."""
    intent = task.docstring
    asserts = _split_asserts(task.test)
    tried = 0
    d1 = [([f"_t1 = {e}"], "_t1") for e in _stage_exprs(params, intent)]
    d2_nodes: list[tuple[list[str], str]] = []
    for lines, out in d1:
        for e in _stage_exprs([out], intent):
            if tried >= budget:
                break
            tried += 1
            yield "\n".join(lines) + f"\nreturn {e}"                         # depth-2 candidate
            d2_nodes.append((lines + [f"_t2 = {e}"], "_t2"))
    if max_depth >= 3 and tried < budget:
        ranked = sorted(
            d2_nodes,
            key=lambda nd: -_partial_score(task, "\n".join(nd[0]) + f"\nreturn {nd[1]}", asserts))
        for lines, out in ranked[:beam]:
            for e in _stage_exprs([out], intent):
                if tried >= budget:
                    return
                tried += 1
                yield "\n".join(lines) + f"\nreturn {e}"                     # depth-3 candidate


# ================================================================= the in-process fast verifier
# For the SEARCH only: our own generated candidates run in a restricted namespace (no import, no I/O,
# no builtins beyond a safe whitelist). Microseconds per candidate, so abstention is cheap. Anything
# that is actually SHIPPED is re-certified by the isolated subprocess oracle (_run_candidate).

_SAFE_BUILTINS: dict[str, Any] = {n: getattr(_builtins, n) for n in (
    "abs all any bool chr dict divmod enumerate filter float frozenset int isinstance iter len "
    "list map max min next ord pow range reversed round set slice sorted str sum tuple zip bytes "
    "ValueError IndexError KeyError TypeError ZeroDivisionError StopIteration ArithmeticError "
    "AttributeError RuntimeError Exception".split())}
_SAFE_BUILTINS.update({"True": True, "False": False, "None": None})


def _exec_ok(signature: str, body: str, test: str) -> bool:
    """Compile signature+body, then run `test` against it in a restricted namespace; True iff nothing
    raises. optimize=0 so asserts are never stripped (even under -O). Safe only for our own generated
    candidates, never advisor drafts."""
    src = signature + "\n" + textwrap.indent(textwrap.dedent(body).strip(), "    ") + "\n"
    ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    try:
        exec(compile(src, "<candidate>", "exec", optimize=0), ns)
        exec(compile(test, "<test>", "exec", optimize=0), ns)
        return True
    except Exception:
        return False


def _run_fast(task: Task, body: str) -> bool:
    """The in-process search gate: run the whole visible test in one shot."""
    return _exec_ok(task.signature, body, task.test)


# ================================================================= the compounding library

_STOP = {"the", "and", "of", "to", "in", "is", "are", "be", "an", "its", "it", "each", "all",
         "that", "for", "from", "with", "as", "or", "if", "else", "given", "into", "them",
         "list", "string", "str", "value", "values", "number", "numbers", "element", "elements"}


def _verbs(docstring: str) -> list[str]:
    """The content tokens of the spec (verbs + salient nouns), stopwords and short noise removed —
    the semantic half of a task's shape."""
    toks = re.findall(r"[a-z]+", docstring.lower())
    return sorted({t for t in toks if len(t) >= 3 and t not in _STOP})


def _types(signature: str) -> str:
    """Parameter type annotations if present, '' each otherwise — the structural half of the shape."""
    m = re.search(r"\(([^)]*)\)", signature)
    if not m:
        return ""
    parts = []
    for p in m.group(1).split(","):
        p = p.strip()
        parts.append(p.split(":", 1)[1].split("=")[0].strip() if ":" in p else "")
    return ",".join(parts)


def _shape(task: Task) -> str:
    """A signature+intent shape key: arity | param-types | content-verbs. Two isomorphic tasks share
    it, so a verified body for one is recalled (and re-verified) for the other."""
    arity = len(_params(task.signature))
    return f"{arity}|{_types(task.signature)}|{','.join(_verbs(task.docstring))}"


def _normalize(body: str, params: list[str]) -> str:
    """Rewrite a solved body param-name-independently: each parameter -> _a{i} (signature order)."""
    for i, p in enumerate(params):
        body = re.sub(rf"\b{re.escape(p)}\b", f"_a{i}", body)
    return body


def _instantiate(template: str, params: list[str]) -> str:
    """Re-fit a stored template to a task's actual parameter names."""
    def sub(m: re.Match) -> str:
        i = int(m.group(1))
        return params[i] if i < len(params) else m.group(0)
    return re.sub(r"_a(\d+)", sub, template)


def _load_library() -> dict[str, list[str]]:
    lib: dict[str, list[str]] = {}
    if LIBRARY.exists():
        for line in LIBRARY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    lib.setdefault(r["shape"], []).append(r["template"])
                except Exception:
                    continue
    return lib


def _remember(task: Task, body: str, params: list[str]) -> None:
    """Mine a solved task into the library, keyed by shape and stored param-normalized (dedup)."""
    shape = _shape(task)
    template = _normalize(body, params)
    if template in _load_library().get(shape, []):
        return
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    with LIBRARY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"shape": shape, "template": template,
                            "intent": task.docstring}, ensure_ascii=False) + "\n")


# ================================================================= the author

@dataclass
class Authored:
    task: str
    body: str | None
    source: str        # library | skeleton | composition | advisor | none
    verified: bool
    tried: int


def _valid(body: str) -> bool:
    try:
        ast.parse("def _f():\n" + textwrap.indent(textwrap.dedent(body).strip(), "    "))
        return True
    except SyntaxError:
        return False


def _certify(task: Task, body: str) -> bool:
    """Ship gate: fast in-process check AND the isolated subprocess oracle must both pass."""
    return _valid(body) and _run_fast(task, body) and _run_candidate(task, body).passed


def author(task: Task, *, advisor: Callable[[Task], str | None] | None = None,
           max_tries: int = 200) -> Authored:
    """Author a verified body for the task, or abstain (body=None). Library -> expression skeletons
    -> block skeletons -> composition -> advisor; every candidate is run through the real test gate,
    and the first to PASS is certified, learned, and returned."""
    tried = 0
    params = _params(task.signature)
    lib = _load_library()

    # 1) learned library — a same-shaped task solved before, re-fit to these params and re-verified
    for template in lib.get(_shape(task), []):
        tried += 1
        body = _instantiate(template, params)
        if _certify(task, body):
            return Authored(task.name, body, "library", True, tried)

    # 2) direct expression skeletons — enumerate structures, verify each
    for fam in EXPR_FAMILIES:
        for expr in fam(params, task.docstring):
            if tried >= max_tries:
                break
            tried += 1
            body = f"return {expr}"
            if _run_fast(task, body) and _certify(task, body):
                _remember(task, body, params)
                return Authored(task.name, body, "skeleton", True, tried)

    # 3) block skeletons — bounded multi-line structures
    for fam in BLOCK_FAMILIES:
        for body in fam(params, task.docstring):
            if tried >= max_tries * 2:
                break
            tried += 1
            if _run_fast(task, body) and _certify(task, body):
                _remember(task, body, params)
                return Authored(task.name, body, "skeleton", True, tried)

    # 4) composition — guided pipelines (depth <= 3) reach tasks no single family reaches
    for body in _compose_guided(task, params):
        tried += 1
        if _certify(task, body):
            _remember(task, body, params)
            return Authored(task.name, body, "composition", True, tried)

    # 5) algorithm schemas — owned scaffolds with small typed holes (costliest, so last). Reaches the
    #    hard rung (DP, topo, backtrack, greedy, stack/scan automata, induced value-maps) without any
    #    task-specific memorized answer; content-learning schemas induce from the task's own examples.
    for sid, body in schema_candidates(params, task.docstring, _parse_examples(task)):
        tried += 1
        if _certify(task, body):
            _remember(task, body, params)
            return Authored(task.name, body, f"schema:{sid}", True, tried)

    # 5.5) induced schemas (L3) — laws the engine ABSTRACTED from its own verified solutions, consulted
    #      AFTER the hand schemas. Structurally applicable (by arity), so an induced law reaches a task
    #      whose wording a hand cue would miss; every body is still isolated-verified. With no induced
    #      store the loop is empty and this step is a no-op (engine == L1/L2).
    from packages.code_reason import schema_induction as _si
    for fam, body in _si.induced_candidates(params, task.docstring, _parse_examples(task)):
        tried += 1
        if _certify(task, body):
            _remember(task, body, params)
            return Authored(task.name, body, f"induced:{fam}", True, tried)

    # 6) advisor draft (optional, UNTRUSTED) — isolated subprocess gate only, never run in-process
    if advisor is not None:
        draft = advisor(task)
        if draft:
            tried += 1
            body = _strip_body(draft)
            if _valid(body) and _run_candidate(task, body).passed:
                _remember(task, body, params)
                return Authored(task.name, body, "advisor", True, tried)

    return Authored(task.name, None, "none", False, tried)   # abstain over a wrong program


def _strip_body(draft: str) -> str:
    """Pull the function body out of an advisor's (possibly fenced, possibly full-def) draft."""
    draft = re.sub(r"^```[a-z]*\n|```$", "", draft.strip(), flags=re.M)
    m = re.search(r"def\s+\w+\s*\([^)]*\)\s*:\s*\n(.+)", draft, re.S)
    if m:
        lines = [ln[4:] if ln.startswith("    ") else ln for ln in m.group(1).splitlines()]
        return "\n".join(lines).strip()
    return draft.strip()


def author_suite(tasks: list[Task], **kw) -> dict[str, Any]:
    """Author a whole suite; report rate + how INDEPENDENT the engine was (own synthesis vs advisor)."""
    results = [author(t, **kw) for t in tasks]
    passed = [r for r in results if r.verified]
    by_src: dict[str, int] = {}
    for r in passed:
        by_src[r.source] = by_src.get(r.source, 0) + 1
    return {
        "n_tasks": len(tasks),
        "authored_pass": len(passed),
        "authorship_rate": round(len(passed) / max(1, len(tasks)), 4),
        "independent_pass": sum(v for k, v in by_src.items()
                                if k in ("library", "skeleton", "composition") or k.startswith("schema")),
        "by_source": by_src,
        "results": [r.__dict__ for r in results],
    }
