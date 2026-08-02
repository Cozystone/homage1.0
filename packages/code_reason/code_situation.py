# -*- coding: utf-8 -*-
"""Code situation model — the situation-model pattern (that took bAbI 0.127→0.9755) applied to CODE.

Prose forced us to EXTRACT the situation graph heuristically; code hands it to us EXACTLY via the
AST. So a function becomes a typed CodeSituation — params, returns, calls, raises, loops, branches,
assignments, self-recursion — and comprehension questions are answered by traversing THAT summary.

The point is not that code comprehension is hard (it is the easy floor precisely because the graph
is exact). The point is that this is the FLOOR of code mastery: read structurally, then modify,
then AUTHOR — and authorship is the one domain with a perfect verifier (the tests), which is why
No-LLM generative reasoning (propose + verify, the AlphaGeometry shape) fits code better than prose.

This organ builds a COMPACT summary and answers from it; the battery computes ground truth by an
INDEPENDENT ast walk. Divergence = the organ's extraction is incomplete (a real signal), not a
tautology. English-only, no pretrained anything: it is a deterministic ast traversal.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class CodeSituation:
    name: str
    params: list[str] = field(default_factory=list)
    returns_value: bool = False
    return_exprs: list[str] = field(default_factory=list)
    calls: set[str] = field(default_factory=set)      # bare callee names
    raises: set[str] = field(default_factory=set)     # NAMED exception types
    has_raise: bool = False                           # ANY raise, incl. bare re-raise (no name)
    has_loop: bool = False
    has_branch: bool = False
    assigns: set[str] = field(default_factory=set)    # names assigned in the body
    is_recursive: bool = False
    n_statements: int = 0


def _callee_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def build(func_src: str) -> CodeSituation | None:
    """Parse ONE function's source into a CodeSituation. None if it does not parse to a function."""
    try:
        tree = ast.parse(func_src)
    except SyntaxError:
        return None
    fn = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    if fn is None:
        return None
    sit = CodeSituation(name=fn.name)
    sit.params = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    if fn.args.vararg:
        sit.params.append("*" + fn.args.vararg.arg)
    if fn.args.kwarg:
        sit.params.append("**" + fn.args.kwarg.arg)
    sit.n_statements = len(fn.body)
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            sit.returns_value = True
            try:
                sit.return_exprs.append(ast.unparse(node.value))
            except Exception:
                pass
        elif isinstance(node, ast.Call):
            c = _callee_name(node)
            if c:
                sit.calls.add(c)
                if c == fn.name:
                    sit.is_recursive = True
        elif isinstance(node, ast.Raise):
            sit.has_raise = True                          # bare 're-raise' counts, even with no name
            exc = node.exc
            if isinstance(exc, ast.Call):
                nm = _callee_name(exc)
            elif isinstance(exc, ast.Name):
                nm = exc.id
            else:
                nm = None
            if nm:
                sit.raises.add(nm)
        elif isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
            sit.has_loop = True
        elif isinstance(node, ast.If):
            sit.has_branch = True
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    sit.assigns.add(t.id)
    return sit


def answer(question: str, sit: CodeSituation) -> str | None:
    """Answer a comprehension question from the situation summary. None => the organ has no
    grounded answer (it abstains — never fabricates, the same honesty floor as everywhere)."""
    q = question.lower().strip().rstrip("?")
    if "how many parameters" in q or "how many arguments" in q:
        return str(len(sit.params))
    if "does it return a value" in q or "does the function return" in q:
        return "yes" if sit.returns_value else "no"
    if "is it recursive" in q or "does it call itself" in q:
        return "yes" if sit.is_recursive else "no"
    if "does it raise" in q or "can it raise" in q:
        return "yes" if sit.has_raise else "no"
    if "does it contain a loop" in q or "does it loop" in q:
        return "yes" if sit.has_loop else "no"
    if "does it have a conditional" in q or "does it branch" in q or "have a branch" in q:
        return "yes" if sit.has_branch else "no"
    if "does it call" in q:                                     # 'does it call the function <x>'
        for name in sorted(sit.calls, key=len, reverse=True):
            if name.lower() in q:
                return "yes"
        return "no"                                            # a named callee not present => no
    return None
