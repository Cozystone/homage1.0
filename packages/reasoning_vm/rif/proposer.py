# -*- coding: utf-8 -*-
"""RIF M2 — the Operator Proposer: generate candidate representations (typed programs) to break a wall.

Four generative sources, in order of how principled they are for a given deficit (BVSR: be prolific and
STRUCTURED; the sandbox critic selects):
  1. LEAP TRANSFER   — take an operator/shape that graduated in ONE module and try it in another
                       (leap.py's structure-transfer applied to the system's OWN feature programs).
  2. PREDICATE TMPL  — a named failure deficit compiles to a program schema. The canonical one for
                       SQuAD-style unanswerability: mentions_but_lacks = sub(align(topic), align(focus))
                       ("the passage matches the entity but NOT the asked attribute").
  3. DUPLICATE-DIVERGE — mutate an existing/seed program (evo-devo Hox): swap an op, swap a leaf,
                       wrap in a unary. Cheap, local, exploits what already works.
  4. TYPED GROWTH    — grammar-random programs for raw diversity / archive filling.

Everything is type-checked at construction, so every proposal is executable. No LLM.
"""
from __future__ import annotations

import random

from . import dsl
from .dsl import Prog, Sig, out_type

_UNARY_S = ["relu", "neg"]


# ── typed random growth ─────────────────────────────────────────────────────────────────────────
def grow(target: str, signals: list[Sig], rng: random.Random, max_depth: int = 3):
    """Build a type-correct program producing `target`. Terminates at signals/consts when depth runs out."""
    leaves = [s for s in signals if s.type == target]
    if max_depth <= 0 or (leaves and rng.random() < 0.45):
        if target == dsl.S and (not leaves or rng.random() < 0.3):
            return round(rng.uniform(-1.0, 1.0), 3)          # scalar const
        if leaves:
            return rng.choice(leaves)
        # no leaf of this type — must build one
    producers = [op for op in dsl.ops_by_output()[target]]
    rng.shuffle(producers)
    for op in producers:
        args = []
        ok = True
        for t in op.in_types:
            sub = grow(t, signals, rng, max_depth - 1)
            if sub is None:
                ok = False
                break
            args.append(sub)
        if ok:
            return Prog(op.name, tuple(args))
    return rng.choice(leaves) if leaves else None


def _subnodes(node):
    yield node
    if isinstance(node, Prog):
        for a in node.args:
            yield from _subnodes(a)


def _replace(node, target, repl):
    """Return a copy of `node` with the first occurrence (by identity) of `target` replaced."""
    if node is target:
        return repl
    if isinstance(node, Prog):
        return Prog(node.op, tuple(_replace(a, target, repl) for a in node.args))
    return node


def mutate(prog, signals: list[Sig], rng: random.Random):
    """Duplicate-and-diverge: pick a subnode and perturb it (swap op with same signature, swap a
    same-typed leaf, or wrap a scalar in a unary). Preserves type-correctness."""
    nodes = list(_subnodes(prog))
    node = rng.choice(nodes)
    kind = rng.random()
    if isinstance(node, Prog):
        alts = [op for op in dsl._OPS.values()
                if op.in_types == dsl._OPS[node.op].in_types and op.out_type == node.out_type
                and op.name != node.op]
        if alts and kind < 0.6:
            return _replace(prog, node, Prog(rng.choice(alts).name, node.args))
        if node.out_type == dsl.S and kind < 0.8:            # wrap a scalar subtree in a unary
            return _replace(prog, node, Prog(rng.choice(_UNARY_S), (node,)))
    if isinstance(node, Sig):
        same = [s for s in signals if s.type == node.type and s.name != node.name]
        if same:
            return _replace(prog, node, rng.choice(same))
    # fallback: regrow a fresh scalar subtree
    return _replace(prog, node, grow(out_type(node), signals, rng, 2))


# ── predicate templates (named deficit → program schema) ─────────────────────────────────────────
def predicate_templates(signals: list[Sig]) -> list:
    """Instantiate structural schemas that a shallow feature CANNOT express as a single primitive.
    These are the compositional programs a representation wall needs — proposed, never asserted."""
    by = {s.name: s for s in signals}
    vecs = [s for s in signals if s.type == dsl.V]
    setv = [s for s in signals if s.type == dsl.SV]
    out = []

    def mk(name_v_topic, name_v_focus, name_sv):
        topic, focus, ss = by.get(name_v_topic), by.get(name_v_focus), by.get(name_sv)
        if topic and focus and ss:
            # mentions_but_lacks: passage aligns to TOPIC but not to the asked FOCUS
            out.append(Prog("sub", (Prog("maxalign", (ss, topic)), Prog("maxalign", (ss, focus)))))
            # peaked single match to focus (a real answer is usually ONE place)
            out.append(Prog("topgap", (ss, focus)))

    def mk_pos(name_ts, name_topic, name_focus):
        """POSITIONAL schemas (grammar amendment): the answer-bearing structure mean-pooling can't see."""
        ts, topic, focus = by.get(name_ts), by.get(name_topic), by.get(name_focus)
        if ts and topic and focus:
            out.append(Prog("ctx_align", (ts, focus, topic)))      # focus-match's context is about topic?
            out.append(Prog("ctx_gap", (ts, focus, topic)))        # concentrated AROUND focus vs anywhere
            out.append(Prog("peak_align", (ts, focus)))            # token-level (undiluted) focus match
            out.append(Prog("sub", (Prog("peak_align", (ts, topic)), Prog("peak_align", (ts, focus)))))

    # try known SQuAD signal names; harmless if absent
    mk("q_topic", "q_focus", "sents")
    mk("q_body", "q_head", "sents")
    mk_pos("ptoks", "q_topic", "q_focus")
    # generic: for every (topic,focus) vec pair over a set, the contrast schema
    for ss in setv[:2]:
        for a in vecs:
            for b in vecs:
                if a.name < b.name:
                    out.append(Prog("sub", (Prog("maxalign", (ss, a)), Prog("maxalign", (ss, b)))))
    return out


# ── leap transfer over programs ──────────────────────────────────────────────────────────────────
def leap_transfer(graduated: list, signals: list[Sig], rng: random.Random) -> list:
    """Re-home a program that worked elsewhere: keep its SHAPE, rebind its leaves to THIS module's
    signals of the same type. This is analogy at the level of feature-programs."""
    out = []
    for prog in graduated:
        remapped = _rebind(prog, signals, rng)
        if remapped is not None:
            out.append(remapped)
    return out


def _rebind(node, signals: list[Sig], rng: random.Random):
    if isinstance(node, Sig):
        cands = [s for s in signals if s.type == node.type]
        return rng.choice(cands) if cands else None
    if isinstance(node, Prog):
        args = [_rebind(a, signals, rng) for a in node.args]
        if any(a is None for a in args):
            return None
        return Prog(node.op, tuple(args))
    return node


# ── the batch ─────────────────────────────────────────────────────────────────────────────────────
def propose_batch(signals: list[Sig], *, seeds: list | None = None, graduated: list | None = None,
                  n: int = 60, seed: int = 0) -> list:
    """A de-duplicated batch of type-valid scalar-output candidate programs."""
    rng = random.Random(seed)
    cands: list = []
    cands += predicate_templates(signals)                     # principled first
    if graduated:
        cands += leap_transfer(graduated, signals, rng)
    if seeds:
        for _ in range(n // 3):
            cands.append(mutate(rng.choice(seeds), signals, rng))
    while len(cands) < n:
        g = grow(dsl.S, signals, rng, max_depth=3)
        if g is not None:
            cands.append(g)
    # keep only scalar-output, de-dup by rendering, drop trivial constants
    seen, out = set(), []
    for c in cands:
        if out_type(c) != dsl.S:
            continue
        key = dsl.render(c)
        if key in seen or isinstance(c, (int, float)):
            continue
        seen.add(key)
        out.append(c)
    return out
