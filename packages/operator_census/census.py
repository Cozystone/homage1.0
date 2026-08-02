# -*- coding: utf-8 -*-
"""G1 — which computations does ATANOR keep re-implementing? Measured by SHAPE, never by name.

Plan v6 rests on a claim that must not be taken on trust: that the generality gap is a
CONSOLIDATION gap, because the same operation was written by hand in four organs in a single day.
A keyword sweep put something of that shape in 30 of 132 organs, and that number was explicitly
labelled a hint -- it came from a grep, and this repository has produced two keyword artifacts in
one day (`sealed_evidence` read off filenames, and a receipt census that credited `base_brain` for
calling its own recorder). Measuring duplication by searching for the word "lift" would be a third.

WHAT A STRUCTURAL SIGNATURE IS HERE. For each function, the AST is reduced to the SHAPE of what it
does and not to what anything is called: which control constructs it uses, in what nesting, which
builtin operations it applies, the arity of its arguments and the shape of what it returns.
Identifiers -- names of functions, variables, arguments, attributes, and every literal -- are
discarded before hashing. Two functions collide only when they compute the same shape, whatever
their vocabulary.

THE GATE THIS HAS TO PASS, and it is a real one: the four known duplicates must fall out WITHOUT
being told about them. A duplication detector that cannot rediscover a duplication we already know
exists is not measuring duplication, and its inventory would be decoration.

Read-only. Reports; consolidates nothing. Which duplicates are worth merging is a judgement made
against the frozen-domain transfer gate, not here.
"""
from __future__ import annotations

import ast
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]

# Shapes this small are shared by everything and say nothing -- a two-node body is not an operator.
MIN_NODES = 12


@dataclass(frozen=True)
class Occurrence:
    organ: str
    module: str
    function: str
    line: int
    nodes: int

    @property
    def where(self) -> str:
        return f"{self.module}:{self.line} {self.function}"


@dataclass(frozen=True)
class RecurringShape:
    """One computation shape and every place it was independently written."""
    signature: str
    occurrences: tuple[Occurrence, ...]
    skeleton: str = ""

    @property
    def organs(self) -> tuple[str, ...]:
        return tuple(sorted({o.organ for o in self.occurrences}))

    @property
    def spread(self) -> int:
        """How many DISTINCT organs hold it. Two copies inside one organ are refactoring debt;
        the same shape in eight organs is the thing plan v6 is about."""
        return len(self.organs)

    def as_dict(self) -> dict[str, Any]:
        return {"signature": self.signature[:16], "spread": self.spread,
                "copies": len(self.occurrences), "organs": list(self.organs),
                "skeleton": self.skeleton,
                "where": [o.where for o in self.occurrences[:6]]}


class _Shape(ast.NodeVisitor):
    """Reduce a function to what it DOES. Every identifier and literal is dropped."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.depth = 0
        self.nodes = 0

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes += 1
        kind = type(node).__name__
        if kind in ("Name", "Attribute", "arg", "alias", "keyword"):
            # identifiers carry the vocabulary, which is exactly what must not decide a match
            self.parts.append("ID")
            for child in ast.iter_child_nodes(node):
                if not isinstance(child, (ast.Name, ast.Attribute)):
                    self.visit(child)
            return
        if isinstance(node, ast.Constant):
            self.parts.append("K")
            return
        if kind in ("For", "While", "If", "comprehension", "IfExp", "Try", "With"):
            self.depth += 1
            self.parts.append(f"{kind}@{min(self.depth, 4)}")
            for child in ast.iter_child_nodes(node):
                self.visit(child)
            self.depth -= 1
            return
        if isinstance(node, ast.BinOp):
            self.parts.append(f"BinOp.{type(node.op).__name__}")
        elif isinstance(node, ast.Compare):
            self.parts.append("Cmp." + ".".join(type(o).__name__ for o in node.ops))
        elif isinstance(node, (ast.BoolOp, ast.UnaryOp)):
            self.parts.append(f"{kind}.{type(node.op).__name__}")
        else:
            self.parts.append(kind)
        for child in ast.iter_child_nodes(node):
            self.visit(child)


def signature_of(fn: ast.AST) -> tuple[str, int, str]:
    """(hash, node count, readable skeleton) for one function."""
    sh = _Shape()
    for stmt in getattr(fn, "body", []):
        sh.visit(stmt)
    text = "|".join(sh.parts)
    return hashlib.sha256(text.encode()).hexdigest(), sh.nodes, text[:160]


def _organs(root: Path) -> list[str]:
    pkgs = root / "packages"
    return sorted(p.name for p in pkgs.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", "."))) if pkgs.is_dir() else []


def scan(root: Path | None = None, *, min_nodes: int = MIN_NODES,
         skip_tests: bool = True) -> dict[str, list[Occurrence]]:
    """signature -> everywhere that shape was written."""
    r = root or REPO
    found: dict[str, list[Occurrence]] = defaultdict(list)
    skeletons: dict[str, str] = {}
    for organ in _organs(r):
        for py in (r / "packages" / organ).rglob("*.py"):
            if "__pycache__" in py.parts or (skip_tests and "test" in py.name):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                sig, nodes, skel = signature_of(node)
                if nodes < min_nodes:
                    continue
                skeletons.setdefault(sig, skel)
                found[sig].append(Occurrence(
                    organ, str(py.relative_to(r)).replace("\\", "/"), node.name, node.lineno, nodes))
    scan.skeletons = skeletons                     # type: ignore[attr-defined]
    return dict(found)


def recurring(root: Path | None = None, *, min_spread: int = 3,
              min_nodes: int = MIN_NODES) -> list[RecurringShape]:
    """Shapes written independently in at least `min_spread` DISTINCT organs, widest first."""
    table = scan(root, min_nodes=min_nodes)
    skeletons = getattr(scan, "skeletons", {})
    out = [RecurringShape(sig, tuple(occ), skeletons.get(sig, ""))
           for sig, occ in table.items()]
    out = [s for s in out if s.spread >= min_spread]
    out.sort(key=lambda s: (-s.spread, -len(s.occurrences)))
    return out


def duplication_report(root: Path | None = None, *, min_spread: int = 3) -> dict[str, Any]:
    """The honest inventory: how much of this codebase is the same computation written again."""
    shapes = recurring(root, min_spread=min_spread)
    organs = _organs(root or REPO)
    touched = sorted({o for s in shapes for o in s.organs})
    return {
        "organs": len(organs),
        "recurring_shapes": len(shapes),
        "organs_holding_a_duplicate": len(touched),
        "duplicate_copies": sum(len(s.occurrences) for s in shapes),
        "widest": [s.as_dict() for s in shapes[:12]],
    }


def find_shape_of(module: str, function: str, root: Path | None = None) -> str | None:
    """The signature of one named function, so a known duplicate can be looked up rather than
    searched for. Used by the gate test, never by the measurement itself."""
    r = root or REPO
    try:
        tree = ast.parse((r / module).read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return signature_of(node)[0]
    return None


def organ_duplication(root: Path | None = None, *, min_spread: int = 3) -> list[tuple[str, int]]:
    """Which organs carry the most re-implemented shapes. The consolidation work list."""
    shapes = recurring(root, min_spread=min_spread)
    counts: Counter = Counter()
    for s in shapes:
        counts.update(s.organs)
    return counts.most_common()
