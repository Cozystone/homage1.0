# -*- coding: utf-8 -*-
"""Failure-signature organ (Switch 1: failure credit assignment) — REAL parts (a)-(c).

The owner's design (docs/ATANOR_meta_diagnosis_loop.md, Switch 1) splits credit-assignment into:
  (a) COLLECT the failed tasks,
  (b) FHRR-ENCODE the I/O DELTA structure of each ("what changed"), and
  (c) CLUSTER the signatures into failure families.
Those three are tractable and are REAL here. The genuinely hard part — (d) mapping a cluster to a
GENUINELY-NEW *named structural hypothesis* — is the frontier (Switch 2 v1) and is NOT done here.

What IS here (honest):
  * ``delta_features``       — extract a SMALL FIXED vocabulary of structural I/O-delta features
                               (booleans + sign categories) from a task's train pairs. No learning.
  * ``failure_signature``    — bundle those features into ONE FHRR phasor signature via the reused
                               ``vsa_reasoning`` algebra (bind role_i with value_i, superpose). Two
                               tasks with the same structural delta resonate ~1.0; a differing
                               feature drops the resonance ~linearly (roles are orthogonal, so
                               resonance ≈ fraction-of-features-that-agree — the discriminative
                               quantity we want for clustering).
  * ``cluster_signatures``   — centroid-linkage agglomerative clustering by phasor resonance with a
                               threshold. Pure numpy. This is (c).
  * ``characterize_cluster`` — return a structural descriptor for a cluster from a FIXED four-word
                               vocabulary {colour-only, shape-only, count-change, relational-
                               suspected}, DERIVED by a fixed decision rule over the delta features.
                               It is NOT a learned namer and it CANNOT mint a new name. Turning a
                               cluster into a genuinely-new named hypothesis (e.g. "relative colour
                               between adjacent objects") is the frontier — see Switch 2 v1 in
                               ``meta_diagnose.propose_novel_module`` (a NotImplementedError stub).

A "task" is: a list of ``(input_grid, output_grid)`` train pairs, plus an OPTIONAL held-out test
pair. Grids are ``list[list[int]]`` with 0 = background. Signatures are computed from the train
pairs (where both sides are known); the test pair is folded in only if its output is provided.
Deterministic, No-LLM, numpy only.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

# Read-only reuse of the holographic algebra (no second implementation).
from packages.vsa_reasoning.fhrr_core import atom, bind, superpose, resonance

Grid = list[list[int]]

# The FIXED delta-feature vocabulary. The role names are the ONLY structural axes we encode; there
# is no learned/open namer. Booleans and small sign categories keep the signature a clean hash.
_FEATURE_ROLES = (
    "shape_preserved",       # grid dimensions unchanged across all pairs
    "colour_only",           # dims + foreground MASK identical, only cell colours differ
    "fg_delta_sign",         # sign of change in #foreground(non-bg) cells: neg/zero/pos/mixed
    "obj_delta_sign",        # sign of change in #connected components (4-conn, colour-agnostic)
    "palette_changed",       # the set of distinct colours changed
    "relational_suspected",  # shape-preserved, changed, not recolour, no count change (rearrange)
    "any_change",            # output differs from input at all
)

# The FIXED cluster-descriptor vocabulary (Switch 1 (d), fixed-rule version — NOT a learned namer).
DESCRIPTOR_VOCAB = ("colour-only", "shape-only", "count-change", "relational-suspected")


# --- grid primitives --------------------------------------------------------------------------
def _dims(g: Grid) -> tuple[int, int]:
    return (len(g), len(g[0]) if g and isinstance(g[0], list) else 0)


def _fg_positions(g: Grid) -> set[tuple[int, int]]:
    return {(r, c) for r, row in enumerate(g) for c, v in enumerate(row) if v != 0}


def _palette(g: Grid) -> frozenset[int]:
    return frozenset(v for row in g for v in row)


def _components(g: Grid) -> int:
    """Number of 4-connected components of non-background (non-zero) cells, colour-agnostic."""
    R, C = _dims(g)
    seen = [[False] * C for _ in range(R)]
    count = 0
    for r in range(R):
        for c in range(C):
            if g[r][c] != 0 and not seen[r][c]:
                count += 1
                stack = [(r, c)]
                seen[r][c] = True
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < R and 0 <= nx < C and not seen[ny][nx] and g[ny][nx] != 0:
                            seen[ny][nx] = True
                            stack.append((ny, nx))
    return count


def _agg_sign(values: Sequence[int]) -> str:
    """Reduce a list of integer deltas to a consistent sign category."""
    if not values:
        return "zero"
    if all(v > 0 for v in values):
        return "pos"
    if all(v < 0 for v in values):
        return "neg"
    if all(v == 0 for v in values):
        return "zero"
    return "mixed"


def _pair_delta(gi: Grid, go: Grid) -> dict[str, Any]:
    """Raw per-pair delta measurements (unaggregated)."""
    di, do = _dims(gi), _dims(go)
    shape_preserved = di == do
    d: dict[str, Any] = {"shape_preserved": shape_preserved}
    d["fg_delta"] = len(_fg_positions(go)) - len(_fg_positions(gi))
    d["obj_delta"] = _components(go) - _components(gi)
    d["palette_changed"] = _palette(gi) != _palette(go)
    if shape_preserved:
        R, C = di
        changed = any(gi[r][c] != go[r][c] for r in range(R) for c in range(C))
        mask_same = _fg_positions(gi) == _fg_positions(go)
        d["any_change"] = changed
        d["colour_only"] = bool(mask_same and changed)
    else:
        d["any_change"] = True
        d["colour_only"] = False
    return d


# --- (b) feature extraction + FHRR encode -----------------------------------------------------
def delta_features(
    train_pairs: Sequence[tuple[Grid, Grid]],
    test_pair: tuple[Grid, Grid | None] | None = None,
) -> dict[str, Any]:
    """Extract the fixed-vocabulary structural delta features for one task (aggregated over its
    train pairs; the test pair is folded in only if its output is present)."""
    pairs = list(train_pairs)
    if test_pair is not None and len(test_pair) == 2 and test_pair[1] is not None:
        pairs = pairs + [(test_pair[0], test_pair[1])]
    if not pairs:
        raise ValueError("delta_features needs at least one (input, output) pair")

    pf = [_pair_delta(gi, go) for gi, go in pairs]
    shape_preserved = all(p["shape_preserved"] for p in pf)
    colour_only = shape_preserved and all(p["colour_only"] for p in pf)
    any_change = any(p["any_change"] for p in pf)
    palette_changed = any(p["palette_changed"] for p in pf)
    fg_delta_sign = _agg_sign([p["fg_delta"] for p in pf])
    obj_delta_sign = _agg_sign([p["obj_delta"] for p in pf])
    relational_suspected = bool(
        shape_preserved and any_change and not colour_only
        and fg_delta_sign == "zero" and obj_delta_sign == "zero"
    )
    return {
        "shape_preserved": bool(shape_preserved),
        "colour_only": bool(colour_only),
        "fg_delta_sign": fg_delta_sign,
        "obj_delta_sign": obj_delta_sign,
        "palette_changed": bool(palette_changed),
        "relational_suspected": relational_suspected,
        "any_change": bool(any_change),
    }


def encode_features(features: dict[str, Any],
                    roles: Sequence[str] | None = None) -> np.ndarray:
    """Bundle the delta-feature dict into one FHRR signature: Σ_i bind(role_i, value_i). Roles are
    orthogonal, so resonance(sig_a, sig_b) ≈ fraction of features whose value agrees.

    `roles` defaults to the ARC delta vocabulary, so every existing caller is byte-identical. It is
    a parameter because the algorithm never knew what a role MEANS -- it only builds atoms from
    strings. Hard-coding the ARC set made the recipe ledger unreachable from any other domain, and
    the workaround was already visible: `self_acceleration/trace_signature.py` copies this function
    verbatim ("Mirrors meta_diagnosis.encode_features exactly") to encode code-synthesis traces. A
    third domain would have meant a third copy. Passing the role set instead is parameterisation,
    not a widened hand list -- the caller owns its own vocabulary."""
    parts = []
    for role in (roles if roles is not None else _FEATURE_ROLES):
        val = features.get(role)
        role_atom = atom(f"__mdfail_role_{role}__")
        # value atom keyed WITH the role so identical value strings under different roles differ
        val_atom = atom(f"__mdfail_val_{role}={val!r}__")
        parts.append(bind(role_atom, val_atom))
    return superpose(*parts)


def failure_signature(
    train_pairs: Sequence[tuple[Grid, Grid]],
    test_pair: tuple[Grid, Grid | None] | None = None,
) -> np.ndarray:
    """FHRR failure-signature of a task: encode its structural I/O delta as one phasor bundle."""
    return encode_features(delta_features(train_pairs, test_pair))


# --- (c) clustering ---------------------------------------------------------------------------
DEFAULT_CLUSTER_THRESHOLD = 0.75


def _centroid(sigs: list[np.ndarray]) -> np.ndarray:
    """Mean phasor bundle of a cluster's member signatures (resonance is scale-invariant, so the
    mean is a faithful representative)."""
    acc = np.zeros_like(sigs[0], dtype=np.complex128)
    for s in sigs:
        acc = acc + s
    return acc / float(len(sigs))


def cluster_signatures(
    signatures: Sequence[np.ndarray],
    task_ids: Sequence[Any],
    *,
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> dict[str, Any]:
    """Centroid-linkage agglomerative clustering by phasor resonance.

    Start each task as its own cluster; repeatedly merge the two clusters whose centroids resonate
    most, stopping once the best inter-centroid resonance falls below ``threshold``. Deterministic
    (ties broken by lowest index). Returns::

        {"clusters": [{"centroid": <complex ndarray>, "member_task_ids": [...], "size": n}, ...]}

    with clusters ordered by descending size then first member id."""
    if len(signatures) != len(task_ids):
        raise ValueError("signatures and task_ids must align")
    n = len(signatures)
    if n == 0:
        return {"clusters": []}

    members: list[list[int]] = [[i] for i in range(n)]
    centroids: list[np.ndarray] = [np.asarray(s, dtype=np.complex128) for s in signatures]

    while len(members) > 1:
        best = (-2.0, -1, -1)
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                r = resonance(centroids[a], centroids[b])
                if r > best[0]:
                    best = (r, a, b)
        if best[0] < threshold:
            break
        _, a, b = best
        members[a] = members[a] + members[b]
        centroids[a] = _centroid([signatures[i] for i in members[a]])
        del members[b]
        del centroids[b]

    clusters = [
        {
            "centroid": centroids[k],
            "member_task_ids": [task_ids[i] for i in members[k]],
            "size": len(members[k]),
        }
        for k in range(len(members))
    ]
    clusters.sort(key=lambda c: (-c["size"], str(c["member_task_ids"][0])))
    return {"clusters": clusters}


# --- (d, fixed-rule ONLY) characterization ----------------------------------------------------
def _descriptor_from_features(f: dict[str, Any]) -> str:
    """Fixed decision rule → a descriptor from ``DESCRIPTOR_VOCAB``. NOT learned, NOT open-vocab."""
    if not f.get("shape_preserved", True):
        return "shape-only"                       # grid dimensions changed (resize / crop / tile)
    if f.get("colour_only"):
        return "colour-only"                      # same mask, only colours remapped
    if f.get("obj_delta_sign", "zero") != "zero" or f.get("fg_delta_sign", "zero") != "zero":
        return "count-change"                     # objects / foreground cells added or removed
    return "relational-suspected"                 # shape-preserved rearrangement (residual bucket)


def characterize_cluster(member_features: Sequence[dict[str, Any]]) -> str:
    """Return a structural descriptor for a failure cluster from the FIXED four-word vocabulary
    ``DESCRIPTOR_VOCAB``, by majority vote of the per-member fixed-rule descriptor.

    HONEST BOUNDARY: this is Switch 1 step (d) in its *tractable, fixed-vocabulary* form only. The
    descriptor is DERIVED by a fixed rule over the delta features — it is NOT a learned namer and it
    can NEVER emit a name outside ``DESCRIPTOR_VOCAB``. Mapping a cluster to a genuinely-NEW named
    hypothesis (inventing the concept "relative colour of adjacent objects" from the data alone) is
    the frontier — Switch 2 v1 — and is deliberately NOT built here (see
    ``meta_diagnose.propose_novel_module``)."""
    if not member_features:
        raise ValueError("characterize_cluster needs at least one member feature dict")
    votes: dict[str, int] = {}
    for f in member_features:
        d = _descriptor_from_features(f)
        votes[d] = votes.get(d, 0) + 1
    # deterministic: highest count, ties broken by DESCRIPTOR_VOCAB order
    return max(DESCRIPTOR_VOCAB, key=lambda d: (votes.get(d, 0), -DESCRIPTOR_VOCAB.index(d)))
