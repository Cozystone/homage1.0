# -*- coding: utf-8 -*-
"""Verifier-guided synthesis for exact rational scalar programs.

This is deliberately separate from ``code_evolver``.  Accepted integer/list kernels already rely on
that interpreter's ``//`` and totalized-zero semantics; changing them globally would silently change
stored skills.  This module instead provides a small, versioned DSL for continuous science quantities:

    ["var", name]
    ["const", small_integer]
    ["op", "+" | "-" | "*" | "/", left, right]

All arithmetic is ``Fraction``-exact.  Invalid syntax, missing variables, zero division, Python floats,
and resource-limit violations return ``None`` -- never a plausible-looking zero.  The synthesizer is a
bottom-up, observationally deduplicated enumerator.  It optimizes only on the supplied training set;
``synthesize_verified`` admits a program only after an explicit, untouched holdout also matches exactly.
"""
from __future__ import annotations

import json
import re
from fractions import Fraction
from hashlib import sha256
from typing import Any, Iterable

from packages.reasoning_vm.quantity import parse_number

DSL = "rational-v1"
OPS = ("+", "-", "*", "/")
SMALL_CONSTANTS = (-2, -1, 0, 1, 2)

DEFAULT_MAX_NODES = 15
DEFAULT_MAX_STEPS = 128
DEFAULT_MAX_BITS = 4096
DEFAULT_MAX_EXP10 = 300
DEFAULT_MAX_STATES = 50_000

HARD_MAX_NODES = 255
HARD_MAX_STEPS = 16_384
HARD_MAX_BITS = 4_096
HARD_MAX_EXP10 = 1_000
HARD_MAX_STATES = 1_000_000
INVALID_NODE_COUNT = 10**18

_EXP_RE = re.compile(r"[eE]([+-]?\d+)")
_VAR_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")


def _valid_vars(vars_: Any) -> bool:
    return isinstance(vars_, list) and 1 <= len(vars_) <= 6 \
        and all(isinstance(var, str) and _VAR_RE.fullmatch(var) is not None for var in vars_) \
        and len(set(vars_)) == len(vars_)


def _int_limit(value: Any, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _exponent_in_range(text: str, max_exp10: int) -> bool:
    digits = text.lstrip("+-").lstrip("0") or "0"
    ceiling = str(max_exp10)
    return len(digits) < len(ceiling) or (len(digits) == len(ceiling) and digits <= ceiling)


def parse_value(value: Any, *, max_bits: int = DEFAULT_MAX_BITS,
                max_exp10: int = DEFAULT_MAX_EXP10) -> Fraction | None:
    """Parse a safe exact scalar.  Binary floats and booleans are rejected by design."""
    if not _int_limit(max_bits, minimum=1, maximum=HARD_MAX_BITS) \
            or not _int_limit(max_exp10, minimum=0, maximum=HARD_MAX_EXP10):
        return None
    if type(value) is Fraction:
        out = value
    elif type(value) is int:
        out = Fraction(value)
    elif type(value) is str:
        token = value.strip()
        if "," in token:
            return None
        exp = _EXP_RE.search(token)
        if exp is not None and not _exponent_in_range(exp.group(1), max_exp10):
            return None
        try:
            out = parse_number(token)
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
        if out is None:
            return None
    else:
        return None
    if out.numerator.bit_length() > max_bits or out.denominator.bit_length() > max_bits:
        return None
    return out


def node_count(tree: Any, *, stop_after: int | None = None) -> int:
    """Count a JSON-tree iteratively; malformed or cyclic structures are invalid."""
    if stop_after is not None and not _int_limit(
        stop_after, minimum=1, maximum=HARD_MAX_NODES,
    ):
        return INVALID_NODE_COUNT
    stack: list[tuple[Any, bool]] = [(tree, False)]
    active_containers: set[int] = set()
    count = 0
    while stack:
        node, leaving = stack.pop()
        ident = id(node)
        if leaving:
            active_containers.remove(ident)
            continue
        if not isinstance(node, (list, tuple)) or not node:
            return INVALID_NODE_COUNT
        if ident in active_containers:
            return INVALID_NODE_COUNT
        active_containers.add(ident)
        count += 1
        if stop_after is not None and count > stop_after:
            return INVALID_NODE_COUNT
        stack.append((node, True))
        if node[0] in ("var", "const") and len(node) == 2:
            continue
        if node[0] == "op" and len(node) == 4:
            stack.extend(((node[3], False), (node[2], False)))
            continue
        return INVALID_NODE_COUNT
    return count


def _bounded(value: Fraction, max_bits: int) -> Fraction | None:
    if value.numerator.bit_length() > max_bits or value.denominator.bit_length() > max_bits:
        return None
    return value


def evaluate(tree: Any, env: dict[str, Any], *, max_nodes: int = DEFAULT_MAX_NODES,
             max_steps: int = DEFAULT_MAX_STEPS, max_bits: int = DEFAULT_MAX_BITS,
             max_exp10: int = DEFAULT_MAX_EXP10) -> Fraction | None:
    """Interpret a rational DSL tree under explicit resource limits."""
    if type(env) is not dict:
        return None
    if not _int_limit(max_nodes, minimum=1, maximum=HARD_MAX_NODES) \
            or not _int_limit(max_steps, minimum=1, maximum=HARD_MAX_STEPS) \
            or not _int_limit(max_bits, minimum=1, maximum=HARD_MAX_BITS) \
            or not _int_limit(max_exp10, minimum=0, maximum=HARD_MAX_EXP10):
        return None
    if node_count(tree, stop_after=max_nodes) == INVALID_NODE_COUNT:
        return None
    steps = [0]

    def ev(node: Any) -> Fraction | None:
        steps[0] += 1
        if steps[0] > max_steps or not isinstance(node, (list, tuple)) or not node:
            return None
        kind = node[0]
        if kind == "var" and len(node) == 2:
            name = node[1]
            if not isinstance(name, str) or name not in env:
                return None
            return parse_value(env[name], max_bits=max_bits, max_exp10=max_exp10)
        if kind == "const" and len(node) == 2:
            value = node[1]
            if isinstance(value, bool) or not isinstance(value, int) or value not in SMALL_CONSTANTS:
                return None
            return Fraction(value)
        if kind != "op" or len(node) != 4 or node[1] not in OPS:
            return None
        left = ev(node[2])
        right = ev(node[3])
        if left is None or right is None:
            return None
        op = node[1]
        if op == "+":
            out = left + right
        elif op == "-":
            out = left - right
        elif op == "*":
            out = left * right
        else:
            if right == 0:
                return None
            out = left / right
        return _bounded(out, max_bits)

    return ev(tree)


def canonical(value: Fraction) -> str:
    """Canonical proof identity.  Display formatting is intentionally a separate concern."""
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def to_source(tree: Any) -> str:
    if tree[0] == "var":
        return str(tree[1])
    if tree[0] == "const":
        return str(tree[1])
    return f"({to_source(tree[2])} {tree[1]} {to_source(tree[3])})"


def _normalize_tests(tests: Iterable[tuple[dict[str, Any], Any]], vars_: list[str],
                     *, max_bits: int, max_exp10: int) -> list[tuple[dict[str, Any], Fraction]] | None:
    if not _valid_vars(vars_):
        return None
    rows: list[tuple[dict[str, Any], Fraction]] = []
    try:
        raw_rows = list(tests)
    except (TypeError, ValueError):
        return None
    for row in raw_rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            return None
        env, want_raw = row
        if not isinstance(env, dict) or set(env) != set(vars_):
            return None
        normalized_env: dict[str, Any] = {}
        for var in vars_:
            value = parse_value(env[var], max_bits=max_bits, max_exp10=max_exp10)
            if value is None:
                return None
            normalized_env[var] = value
        want = parse_value(want_raw, max_bits=max_bits, max_exp10=max_exp10)
        if want is None:
            return None
        rows.append((normalized_env, want))
    return rows


def fitness(tree: Any, tests: Iterable[tuple[dict[str, Any], Any]], **limits: Any) -> float:
    eval_limits = {
        k: v for k, v in limits.items()
        if k in {"max_nodes", "max_steps", "max_bits", "max_exp10"}
    }
    max_bits = eval_limits.get("max_bits", DEFAULT_MAX_BITS)
    max_exp10 = eval_limits.get("max_exp10", DEFAULT_MAX_EXP10)
    rows: list[tuple[dict[str, Fraction], Fraction]] = []
    try:
        raw_rows = list(tests)
    except (TypeError, ValueError):
        return 0.0
    for row in raw_rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            return 0.0
        env, want_raw = row
        if not isinstance(env, dict) or not env:
            return 0.0
        normalized_env: dict[str, Fraction] = {}
        for name, value_raw in env.items():
            if not isinstance(name, str):
                return 0.0
            value = parse_value(value_raw, max_bits=max_bits, max_exp10=max_exp10)
            if value is None:
                return 0.0
            normalized_env[name] = value
        want = parse_value(want_raw, max_bits=max_bits, max_exp10=max_exp10)
        if want is None:
            return 0.0
        rows.append((normalized_env, want))
    if not rows:
        return 0.0
    hits = 0
    for env, want in rows:
        got = evaluate(tree, env, **eval_limits)
        hits += int(got == want)
    return hits / len(rows)


def _signature(tree: Any, rows: list[tuple[dict[str, Any], Fraction]],
               limits: dict[str, int]) -> tuple[Fraction | None, ...]:
    return tuple(evaluate(tree, env, **limits) for env, _want in rows)


def evolve(tests: list[tuple[dict[str, Any], Any]], vars_: list[str], *,
           max_nodes: int = DEFAULT_MAX_NODES, max_steps: int = DEFAULT_MAX_STEPS,
           max_bits: int = DEFAULT_MAX_BITS, max_exp10: int = DEFAULT_MAX_EXP10,
           max_states: int = DEFAULT_MAX_STATES) -> dict[str, Any]:
    """Find the smallest exact program by bottom-up enumeration and semantic deduplication."""
    if not _int_limit(max_nodes, minimum=1, maximum=HARD_MAX_NODES) \
            or not _int_limit(max_steps, minimum=1, maximum=HARD_MAX_STEPS) \
            or not _int_limit(max_bits, minimum=1, maximum=HARD_MAX_BITS) \
            or not _int_limit(max_exp10, minimum=0, maximum=HARD_MAX_EXP10) \
            or not _int_limit(max_states, minimum=1, maximum=HARD_MAX_STATES):
        return {"solved": False, "tree": None, "program": None, "fitness": 0.0,
                "states": 0, "verdict": "invalid resource limits"}
    if not _valid_vars(vars_):
        return {"solved": False, "tree": None, "program": None, "fitness": 0.0,
                "verdict": "invalid variable list"}
    limits = {"max_nodes": max_nodes, "max_steps": max_steps,
              "max_bits": max_bits, "max_exp10": max_exp10}
    rows = _normalize_tests(tests, vars_, max_bits=max_bits, max_exp10=max_exp10)
    if not rows:
        return {"solved": False, "tree": None, "program": None, "fitness": 0.0,
                "verdict": "invalid or empty training examples"}
    target = tuple(want for _env, want in rows)

    by_size: dict[int, list[list[Any]]] = {1: []}
    seen_signatures: dict[tuple[Fraction | None, ...], list[Any]] = {}
    for leaf in ([["var", v] for v in vars_] + [["const", c] for c in SMALL_CONSTANTS]):
        sig = _signature(leaf, rows, limits)
        if sig in seen_signatures:
            continue
        if len(seen_signatures) >= max_states:
            return {
                "solved": False, "tree": None, "program": None,
                "fitness": 0.0, "states": len(seen_signatures),
                "verdict": "state budget exhausted",
            }
        seen_signatures[sig] = leaf
        by_size[1].append(leaf)
        if sig == target:
            return {"solved": True, "tree": leaf, "program": to_source(leaf), "fitness": 1.0,
                    "states": len(seen_signatures), "verdict": "exact training fit"}

    for size in range(3, max_nodes + 1, 2):
        bucket: list[list[Any]] = []
        for left_size in range(1, size - 1, 2):
            right_size = size - 1 - left_size
            for left in by_size.get(left_size, []):
                for right in by_size.get(right_size, []):
                    for operator in OPS:
                        # Commutative mirror images have identical semantics and larger search cost.
                        if operator in ("+", "*") and json.dumps(left) > json.dumps(right):
                            continue
                        tree = ["op", operator, left, right]
                        sig = _signature(tree, rows, limits)
                        if sig in seen_signatures:
                            continue
                        if len(seen_signatures) >= max_states:
                            return {
                                "solved": False, "tree": None, "program": None,
                                "fitness": 0.0, "states": len(seen_signatures),
                                "verdict": "state budget exhausted",
                            }
                        seen_signatures[sig] = tree
                        bucket.append(tree)
                        if sig == target:
                            return {
                                "solved": True, "tree": tree, "program": to_source(tree),
                                "fitness": 1.0, "states": len(seen_signatures),
                                "verdict": "exact training fit",
                            }
        by_size[size] = bucket
    return {"solved": False, "tree": None, "program": None, "fitness": 0.0,
            "states": len(seen_signatures), "verdict": "no exact program within bounds"}


def examples_digest(tests: Iterable[tuple[dict[str, Any], Any]], vars_: list[str], *,
                    max_bits: int = DEFAULT_MAX_BITS,
                    max_exp10: int = DEFAULT_MAX_EXP10) -> str:
    """Order-independent digest over canonical exact numbers, never raw spelling."""
    if not _valid_vars(vars_):
        raise ValueError("invalid variable list")
    rows = _normalize_tests(tests, vars_, max_bits=max_bits, max_exp10=max_exp10)
    if rows is None:
        raise ValueError("invalid rational examples")
    payload = [
        {"inputs": {v: canonical(env[v]) for v in vars_}, "output": canonical(want)}
        for env, want in rows
    ]
    payload.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def _rejected(verdict: str) -> dict[str, Any]:
    return {
        "solved": False, "accepted": False, "tree": None, "program": None,
        "fitness": 0.0, "holdout_fitness": 0.0, "verdict": verdict,
    }


def synthesize_verified(train_tests: list[tuple[dict[str, Any], Any]],
                        holdout_tests: list[tuple[dict[str, Any], Any]],
                        vars_: list[str], **limits: Any) -> dict[str, Any]:
    """Synthesize on train only, then require exact fitness 1.0 on a disjoint explicit holdout."""
    if not _valid_vars(vars_):
        return _rejected("invalid variable list")
    if not isinstance(train_tests, list) or not isinstance(holdout_tests, list):
        return _rejected("train and holdout examples must be lists")
    max_bits = limits.get("max_bits", DEFAULT_MAX_BITS)
    max_exp10 = limits.get("max_exp10", DEFAULT_MAX_EXP10)
    train_rows = _normalize_tests(
        train_tests, vars_, max_bits=max_bits, max_exp10=max_exp10,
    )
    holdout_rows = _normalize_tests(
        holdout_tests, vars_, max_bits=max_bits, max_exp10=max_exp10,
    )
    if train_rows is None or holdout_rows is None:
        return _rejected("invalid train or holdout example")
    if len(train_rows) < 2 or len(holdout_rows) < 2:
        return _rejected("need >=2 train and >=2 explicit holdout examples")

    train_inputs = [tuple(env[v] for v in vars_) for env, _want in train_rows]
    holdout_inputs = [tuple(env[v] for v in vars_) for env, _want in holdout_rows]
    if len(set(train_inputs)) != len(train_inputs) or len(set(holdout_inputs)) != len(holdout_inputs):
        return _rejected("duplicate canonical inputs within train or holdout partition")
    if set(train_inputs) & set(holdout_inputs):
        return _rejected("train and holdout inputs overlap after exact canonicalization")

    res = evolve(train_rows, vars_, **limits)
    tree = res.get("tree")
    holdout_fit = fitness(tree, holdout_rows, **{
        k: v for k, v in limits.items()
        if k in {"max_nodes", "max_steps", "max_bits", "max_exp10"}
    }) if tree is not None else 0.0
    accepted = bool(res.get("solved")) and holdout_fit == 1.0
    return {
        **res,
        "accepted": accepted,
        "holdout_fitness": holdout_fit,
        "train_digest": examples_digest(
            train_rows, vars_, max_bits=max_bits, max_exp10=max_exp10,
        ),
        "holdout_digest": examples_digest(
            holdout_rows, vars_, max_bits=max_bits, max_exp10=max_exp10,
        ),
        "verdict": "accepted: exact train + disjoint explicit holdout" if accepted
        else "rejected: no exact train program or disjoint holdout failed",
    }
