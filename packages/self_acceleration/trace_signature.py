# -*- coding: utf-8 -*-
"""H4 — FAILURE SIGNATURE over the SYNTHESIS TRACE (Switch 1 (b), the analog the owner sanctioned).

`packages/meta_diagnosis/failure_signature.py` encodes the I/O delta of an ARC GRID task. A synthesis
WALL is a different object: the target is I/O examples (env -> value) and the "failure" is a property of
the SEARCH TRACE — what structure the current vocabulary could not express. This module is the analog
the H4 spec calls for: extract a SMALL FIXED vocabulary of structural trace features ("what could not be
expressed": scalar output, output is a selected input member, output bounded by an extremum, and — the
decisive one — a FUNCTIONAL CONFLICT in the identity-fold deduction, the honest "the accumulator state
is INSUFFICIENT" signal X4.5 named), then bundle them into ONE FHRR phasor signature via the REUSED
`vsa_reasoning` algebra (bind role_i x value_i, superpose), exactly as `meta_diagnosis.encode_features`
does. Two walls with the same structural gap resonate ~1.0; a differing feature drops resonance ~linearly
(orthogonal roles), so the ledger can cluster the k-th-order-statistic walls into one family and RETRIEVE
the scheme that cracked the resonant one — which the proposer then EXTENDS (the generative step) rather
than blindly replaying (which would be mere retrieval).

Deterministic, No-LLM, numpy + stdlib only. Reuses fhrr_core (no second algebra).
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from packages.vsa_reasoning.fhrr_core import atom, bind, superpose, resonance
from packages.evolution import open_domain as od
from packages.evolution import scheme_synthesis as ss

# The FIXED structural-trace feature vocabulary — the only axes we encode. No learned/open namer.
_FEATURE_ROLES = (
    "out_type",              # "scalar" | "seq"           — shape of what could not be built
    "out_is_member",         # output always an element of the input list (a SELECTION)
    "out_le_max",            # output always <= max(input)  (extremum-bounded selection)
    "out_ge_min",            # output always >= min(input)
    "scalar_fold_conflict",  # identity (k=1) fold deduction CONFLICTS -> scalar accumulator insufficient
    "input_family",          # "seq" | "num"              — the domain
)


def _xs(env: dict) -> tuple:
    v = env.get("xs")
    return tuple(v) if isinstance(v, (tuple, list, str)) else ()


def conflict_from_outer(outer: Sequence[tuple], listvar: str = "xs") -> bool:
    """Does the X4.4 identity-fold deduction hit a FUNCTIONAL CONFLICT on PREFIX-CLOSED oracle I/O
    (same (acc, elem) forced to two different next accumulators)? That is the honest signal that a plain
    scalar accumulator cannot express the target — i.e. a projection/richer-state scheme is needed.
    Reuses the real `derive_fold_step_examples`. `outer` MUST be prefix-closed (as `Wall.outer` /
    ss.prefix_closed_io produce) so the deduction has chains to unroll — a synthesis system legitimately
    queries the oracle on prefixes (X4.4 discipline)."""
    lut = {tuple(env.get(listvar, ())): want for env, want in outer}
    init = lut.get((), 0)
    derived = ss.derive_fold_step_examples(list(outer), listvar, init)
    seen_map: dict = {}
    for env, want in derived:
        key = (repr(env[ss._A]), repr(env[ss._E]))
        if key in seen_map and seen_map[key] != want:
            return True
        seen_map[key] = want
    return False


def trace_features(spec: Sequence[tuple], *, conflict: bool | None = None) -> dict[str, Any]:
    """Extract the fixed-vocabulary structural trace features from a target's I/O examples `spec`
    (= [(env, output)]). Aggregated over all examples (a feature holds only if it holds on every one).
    `conflict` is the prefix-closed scalar-fold-conflict flag (computed by the caller via
    `conflict_from_outer`, which needs oracle prefix access); if None we conservatively report False."""
    outs = [o for _e, o in spec]
    is_scalar = all(isinstance(o, int) for o in outs)
    out_type = "scalar" if is_scalar else "seq"
    member = True
    le_max = True
    ge_min = True
    for env, o in spec:
        xs = _xs(env)
        if isinstance(o, int) and xs:
            member = member and (o in xs)
            le_max = le_max and (o <= max(xs))
            ge_min = ge_min and (o >= min(xs))
        elif isinstance(o, int) and not xs:
            member = member and (o == 0)          # empty-input convention (kth_desc(()) == 0)
        else:
            member = le_max = ge_min = False
    conflict = bool(conflict) if conflict is not None else False
    fam = "seq" if any("xs" in e for e, _ in spec) else "num"
    return {
        "out_type": out_type,
        "out_is_member": bool(is_scalar and member),
        "out_le_max": bool(is_scalar and le_max),
        "out_ge_min": bool(is_scalar and ge_min),
        "scalar_fold_conflict": bool(conflict),
        "input_family": fam,
    }


def encode_features(features: dict[str, Any]) -> np.ndarray:
    """Bundle the trace-feature dict into one FHRR signature: sum_i bind(role_i, value_i). Roles are
    orthogonal, so resonance(sig_a, sig_b) ~ fraction of features that agree (the discriminative quantity
    for ledger clustering). Mirrors meta_diagnosis.failure_signature.encode_features exactly."""
    parts = []
    for role in _FEATURE_ROLES:
        val = features.get(role)
        role_atom = atom(f"__h4trace_role_{role}__")
        val_atom = atom(f"__h4trace_val_{role}={val!r}__")
        parts.append(bind(role_atom, val_atom))
    return superpose(*parts)


def signature(spec: Sequence[tuple], *, conflict: bool | None = None) -> np.ndarray:
    """FHRR failure-signature of a synthesis wall: encode its structural trace features as one phasor."""
    return encode_features(trace_features(spec, conflict=conflict))


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Phasor resonance in [-1, 1] between two wall signatures (reused fold-core physics)."""
    return float(resonance(a, b))
