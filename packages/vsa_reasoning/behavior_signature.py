# -*- coding: utf-8 -*-
"""Holographic search guidance — rank candidate primitives by behaviour, pure algebra, no training.

A synthesis search over a primitive library is expensive because it VERIFIES every candidate on every
train pair. VSA offers a cheap pre-ranking: encode a primitive's BEHAVIOUR (its outputs on a fixed
probe battery) as ONE fixed-size FHRR signature, encode the SPEC (the desired input→output examples)
the same way, and rank candidates by phasor resonance to the spec signature. A candidate that
reproduces the spec's outputs has an (almost) identical signature → resonance ≈ 1; one that differs
on k of n probes drops smoothly. So the true primitive floats to the top and the exact verifier only
has to confirm the top few — the signature is a holographic hash of the I/O table.

Signature construction (a VSA key–value store): each probe index i gets an orthogonal ROLE atom
r_i; the behaviour is  Σ_i  bind(r_i, encode(output_i)).  Because the roles are orthogonal, the
resonance between two signatures is (up to crosstalk) the average per-probe agreement of the encoded
outputs — exactly the discriminative quantity we want. Deterministic, No-LLM.

``rank_candidates`` is the reusable API for a later synthesis integration. It is NOT wired into the
evolution package here (a concurrent agent owns that); it is a standalone ranker.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from packages.vsa_reasoning.fhrr_core import atom, bind, resonance

Grid = list[list[int]]


def _is_grid(x) -> bool:
    return isinstance(x, list) and len(x) > 0 and all(isinstance(r, list) for r in x)


def _grid_vec(g: Grid) -> np.ndarray:
    """Encode a grid as a bundle of bound (position, colour) cells plus a shape marker. Two grids that
    agree on most cells resonate strongly; different shapes resonate weakly (shape atom differs)."""
    R = len(g)
    C = len(g[0]) if R and isinstance(g[0], list) else 0
    acc = atom(f"__shape_{R}x{C}__").astype(np.complex128)
    for r in range(R):
        row = g[r]
        for c in range(len(row)):
            acc = acc + bind(atom(f"__pos_{r}_{c}__"), atom(f"__col_{int(row[c])}__"))
    return acc


def _value_vec(x) -> np.ndarray:
    """Encode an arbitrary probe value: a grid via ``_grid_vec``, anything else via its string atom."""
    if _is_grid(x):
        return _grid_vec(x)
    return atom(f"__val_{x!r}__").astype(np.complex128)


def _role(i: int) -> np.ndarray:
    return atom(f"__vsa_probe_role_{i}__")


def behavior_signature(primitive: Callable, probes: Sequence) -> np.ndarray:
    """FHRR signature of a primitive's behaviour on a fixed probe battery:
    Σ_i bind(role_i, encode(primitive(probe_i))). A probe on which the primitive errors contributes
    a fixed 'error' atom (so two primitives that both fail there still agree there)."""
    acc = np.zeros_like(atom("__zero__"), dtype=np.complex128)
    for i, p in enumerate(probes):
        try:
            out = primitive(p)
            ov = _value_vec(out)
        except Exception:
            ov = atom("__vsa_error__").astype(np.complex128)
        acc = acc + bind(_role(i), ov)
    return acc


def spec_signature(examples: Sequence[tuple]) -> np.ndarray:
    """FHRR signature of a target behaviour given (input, output) examples: Σ_i bind(role_i,
    encode(output_i)). The probe battery is the examples' inputs (index-aligned with the roles)."""
    acc = np.zeros_like(atom("__zero__"), dtype=np.complex128)
    for i, (_in, out) in enumerate(examples):
        acc = acc + bind(_role(i), _value_vec(out))
    return acc


def rank_candidates(
    spec_examples: Sequence[tuple],
    candidates: Sequence[Callable] | dict[str, Callable],
) -> list[tuple]:
    """Rank candidate primitives by phasor similarity of their behaviour to the spec.

    ``spec_examples``: (input, output) pairs describing the desired transformation.
    ``candidates``: an iterable of callables, or a {name: callable} map.
    Returns a list of (label, score) sorted by score DESC — the intended search order for a
    downstream exact verifier. Pure algebra, no training. The probe battery is the spec inputs."""
    probes = [i for i, _o in spec_examples]
    target = spec_signature(spec_examples)
    if isinstance(candidates, dict):
        items = list(candidates.items())
    else:
        items = [(getattr(fn, "__name__", f"cand_{k}"), fn) for k, fn in enumerate(candidates)]
    scored = []
    for label, fn in items:
        sig = behavior_signature(fn, probes)
        scored.append((label, float(resonance(target, sig)), fn))
    scored.sort(key=lambda t: t[1], reverse=True)
    return [(label, score) for label, score, _fn in scored]
