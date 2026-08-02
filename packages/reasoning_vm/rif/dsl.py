# -*- coding: utf-8 -*-
"""RIF M1 — the typed featurizer DSL: the LANGUAGE in which a representation is a program.

A "feature" stops being a line of hand-code and becomes a typed program over SIGNAL leaves the
environment exposes (embeddings, sets of embeddings, scalars). This is what makes representation
INVENTABLE: the proposer (M2) searches programs in this grammar, sandbox trials (M3) compile and score
them, graduation (M4) admits a winner AS A NEW LEAF so the next search composes on top of it — the
envelope expands. Types keep the search space finite and every proposal executable.

Types:  V = vector (D)  ·  SV = set of vectors (N×D)  ·  S = scalar  ·  TSEQ = ORDERED token sequence (M×D)
TSEQ is the 2026-07-15 grammar amendment (owner-approved): positional token operators can express
"the best match to the asked focus has the topic IN ITS LOCAL CONTEXT" — a compositional, order-aware
signal that mean-pooled alignment (V/SV) provably cannot, which is exactly the SQuAD-2 gate wall.
No LLM. Pure numpy. Deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

V, SV, S, TSEQ = "V", "SV", "S", "TSEQ"


@dataclass(frozen=True)
class Op:
    name: str
    in_types: tuple[str, ...]
    out_type: str
    fn: Callable[..., Any]
    commutative: bool = False


def _safe_dot(a, b):
    return float(np.dot(a, b))


def _maxalign(sv, v):
    if sv is None or len(sv) == 0:
        return 0.0
    return float(np.max(sv @ v))


def _meanalign(sv, v):
    if sv is None or len(sv) == 0:
        return 0.0
    return float(np.mean(sv @ v))


def _topgap(sv, v):
    """best minus second-best alignment over a set — 'is there ONE standout match?' (peakedness)."""
    if sv is None or len(sv) < 2:
        return 0.0
    a = np.sort(sv @ v)[::-1]
    return float(a[0] - a[1])


# ── positional token-sequence operators (the grammar amendment) ───────────────────────────────────
def _peak_align(ts, v):
    """max cosine of ANY token to a query — finer than sentence-mean (no dilution across a sentence)."""
    if ts is None or len(ts) == 0:
        return 0.0
    return float(np.max(ts @ v))


def _ctx_align(ts, vf, vc, w: int = 4):
    """THE compositional primitive: find the token best matching the FOCUS vf, then measure how well its
    LOCAL WINDOW (±w neighbours) aligns to a context vc. Answerable ≈ the asked thing appears AND its
    surroundings are about the question's topic. Order-dependent — mean-pooling cannot express this."""
    if ts is None or len(ts) < 2:
        return 0.0
    i = int(np.argmax(ts @ vf))
    lo, hi = max(0, i - w), min(len(ts), i + w + 1)
    win = ts[lo:hi]
    if len(win) == 0:
        return 0.0
    return float(np.mean(win @ vc))


def _ctx_gap(ts, vf, vc, w: int = 4):
    """Contrast form: focus-token's context match to vc MINUS the passage's global peak to vc —
    'is the topic concentrated AROUND the focus, or just present somewhere?'"""
    if ts is None or len(ts) < 2:
        return 0.0
    return _ctx_align(ts, vf, vc, w) - _peak_align(ts, vc)


# ── operator library (base primitives; graduated programs get added as leaves, not ops) ───────────
_OPS: dict[str, Op] = {}


def _reg(op: Op):
    _OPS[op.name] = op


_reg(Op("dot", (V, V), S, _safe_dot, commutative=True))
_reg(Op("absdiff", (V, V), S, lambda a, b: float(np.linalg.norm(a - b)), commutative=True))
_reg(Op("maxalign", (SV, V), S, _maxalign))
_reg(Op("meanalign", (SV, V), S, _meanalign))
_reg(Op("topgap", (SV, V), S, _topgap))
_reg(Op("hadamard", (V, V), V, lambda a, b: a * b, commutative=True))
_reg(Op("vsub", (V, V), V, lambda a, b: a - b))
_reg(Op("vadd", (V, V), V, lambda a, b: a + b, commutative=True))
_reg(Op("sub", (S, S), S, lambda a, b: float(a - b)))
_reg(Op("mul", (S, S), S, lambda a, b: float(a * b), commutative=True))
_reg(Op("add", (S, S), S, lambda a, b: float(a + b), commutative=True))
_reg(Op("smin", (S, S), S, lambda a, b: float(min(a, b)), commutative=True))
_reg(Op("smax", (S, S), S, lambda a, b: float(max(a, b)), commutative=True))
_reg(Op("relu", (S,), S, lambda a: float(max(0.0, a))))
_reg(Op("neg", (S,), S, lambda a: float(-a)))
_reg(Op("peak_align", (TSEQ, V), S, _peak_align))
_reg(Op("ctx_align", (TSEQ, V, V), S, _ctx_align))
_reg(Op("ctx_gap", (TSEQ, V, V), S, _ctx_gap))


def ops_by_output() -> dict[str, list[Op]]:
    out: dict[str, list[Op]] = {V: [], SV: [], S: [], TSEQ: []}
    for op in _OPS.values():
        out[op.out_type].append(op)
    return out


# ── program tree ──────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Sig:
    """A typed signal leaf — a named input the environment binds per sample (or a graduated feature)."""
    name: str
    type: str


@dataclass(frozen=True)
class Prog:
    op: str
    args: tuple = ()

    @property
    def out_type(self) -> str:
        return _OPS[self.op].out_type


Node = Any  # Sig | Prog | float


def out_type(node: Node) -> str:
    if isinstance(node, Sig):
        return node.type
    if isinstance(node, Prog):
        return node.out_type
    return S            # bare float const


def depth(node: Node) -> int:
    if isinstance(node, Prog):
        return 1 + max((depth(a) for a in node.args), default=0)
    return 0


def size(node: Node) -> int:
    if isinstance(node, Prog):
        return 1 + sum(size(a) for a in node.args)
    return 1


def render(node: Node) -> str:
    if isinstance(node, Sig):
        return node.name
    if isinstance(node, Prog):
        return f"{node.op}(" + ", ".join(render(a) for a in node.args) + ")"
    return f"{float(node):.3g}"


def evaluate(node: Node, bindings: dict[str, Any]) -> Any:
    """Evaluate a program on one sample's signal bindings. Returns V/SV array or float per out_type."""
    if isinstance(node, Sig):
        return bindings.get(node.name)
    if isinstance(node, (int, float)):
        return float(node)
    op = _OPS[node.op]
    vals = [evaluate(a, bindings) for a in node.args]
    if any(v is None for v in vals):
        return 0.0 if op.out_type == S else None
    try:
        return op.fn(*vals)
    except Exception:
        return 0.0 if op.out_type == S else None


def compile_scalar(node: Node, samples: list[dict[str, Any]]) -> np.ndarray:
    """A program whose out_type is S becomes a FEATURE COLUMN over samples. Non-finite → 0."""
    col = np.array([evaluate(node, s) for s in samples], dtype=np.float64)
    col[~np.isfinite(col)] = 0.0
    return col.astype(np.float32)
