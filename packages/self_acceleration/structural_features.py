# -*- coding: utf-8 -*-
"""H4 v2 — STRUCTURAL FEATURES: the recogniser's read of a synthesis failure signature.

WHY THIS FILE (the v2 frontier, one layer down)
-----------------------------------------------
v1's proposer ranks candidate schemes with HAND-DERIVED prototypes (`proposer._prototype_of`) over a
FIXED move-set ({range, sum} computed recipes + the order-stat grow). The v1 module docstrings name the
one place a small LEARNED recogniser turns recombination into open-ended generation: a model trained on
(failure-signature -> winning move-composition) that PREDICTS the composition from a NOVEL signature,
INCLUDING across families. This module is that recogniser's INPUT — the failure signature as a numeric
feature vector.

It is a SUPERSET of v1's `trace_signature.trace_features` (the same 6 structural-trace axes are the first
features here) extended with GENERIC BEHAVIOURAL PROBES of the target: monotonicity of the output under
prefix growth, per-element increment shape, extremal-update shape, permutation invariance, length
correlation, boundedness. Every feature is a RECOGNITION property ("what shape of computation is this",
the X4.5 "recognition vocabulary, not the answer" discipline) computed from I/O ALONE — never the answer.
The probes query the reference oracle on CONSTRUCTED inputs (prefixes, permutations, length ladders),
which is the same legitimate oracle access v1's `conflict_from_outer` uses (a synthesis system may show
the oracle sort([3]), sort([3,1]), ...). No feature reveals which primitive/aggregate the wall computes;
the recogniser must LEARN the feature -> move mapping from the ledger, and that mapping is what either
transfers to a held-out family or does not.

REUSE: v1's `trace_signature` (trace_features + the FHRR signature for ledger retrieval, unchanged) and
`vsa_reasoning` (via trace_signature). This module adds only the numeric probe vector. No LLM, numpy +
stdlib, deterministic (seeded probes).
"""
from __future__ import annotations

import random
from typing import Any, Callable, Sequence

import numpy as np

from packages.self_acceleration import trace_signature as tsig

# The FIXED, ORDERED structural-feature vocabulary. Index positions are the recogniser's input dims;
# they never change once trained. First block = v1 trace features (spec-derived); second block =
# behavioural probes (oracle-queried on constructed inputs). All values are floats in [0, 1].
FEATURE_NAMES: tuple[str, ...] = (
    # --- v1 trace features (spec-derived; the same axes the FHRR ledger signature encodes) ---
    "out_is_member",        # frac of examples whose output is an element of the input list (a SELECTION)
    "out_le_max",           # frac output <= max(input)              (extremum-bounded above)
    "out_ge_min",           # frac output >= min(input)              (extremum-bounded below)
    "out_exceeds_max",      # frac output >  max(input)              (accumulator that outgrows the data)
    "out_below_min",        # frac output <  min(input)
    "out_nonneg",           # frac output >= 0
    "out_eq_len",           # frac output == len(input)             (count fingerprint)
    "scalar_fold_conflict", # identity scalar fold deduction CONFLICTS -> richer state needed (0/1)
    # --- behavioural probes (oracle queried on constructed inputs) ---
    "mono_up",              # frac of prefix-extension steps with delta_out >= 0   (running_max/sum/cnt)
    "mono_down",            # frac of prefix-extension steps with delta_out <= 0   (running_min)
    "delta_is_one",         # frac of steps with delta_out == 1                    (running_cnt)
    "delta_is_elem",        # frac of steps with delta_out == appended element     (running_sum)
    "extremal_up",          # frac of steps with new_out == max(old_out, elem)     (running_max)
    "extremal_down",        # frac of steps with new_out == min(old_out, elem)     (running_min)
    "perm_invariant",       # frac of permutation probes that preserve the output  (order-independent)
    "len_correlation",      # (corr(output, length)+1)/2 over a length ladder      (grows with n?)
    "singleton_is_input",   # frac where output on a 1-element list [a] equals a   (extremal/order vs tally)
)

N_FEATURES = len(FEATURE_NAMES)


def _xs(env: dict, listvar: str = "xs") -> tuple:
    v = env.get(listvar)
    return tuple(v) if isinstance(v, (tuple, list, str)) else ()


def _spec_features(spec: Sequence[tuple], listvar: str) -> dict[str, float]:
    """The spec-derived block: fractions over the (env, output) examples with a non-empty input."""
    n = mem = le = ge = ex = bl = nn = eqlen = 0
    for env, o in spec:
        xs = _xs(env, listvar)
        if not isinstance(o, int) or not xs:
            continue
        n += 1
        mem += (o in xs)
        le += (o <= max(xs))
        ge += (o >= min(xs))
        ex += (o > max(xs))
        bl += (o < min(xs))
        nn += (o >= 0)
        eqlen += (o == len(xs))
    if n == 0:
        return {k: 0.0 for k in ("out_is_member", "out_le_max", "out_ge_min", "out_exceeds_max",
                                 "out_below_min", "out_nonneg", "out_eq_len")}
    return {
        "out_is_member": mem / n, "out_le_max": le / n, "out_ge_min": ge / n,
        "out_exceeds_max": ex / n, "out_below_min": bl / n, "out_nonneg": nn / n, "out_eq_len": eqlen / n,
    }


def _probe_features(oracle: Callable[[tuple], Any], rng: random.Random, *, lo: int, hi: int,
                    max_len: int, n_lists: int = 24) -> dict[str, float]:
    """The behavioural block. Query the oracle on constructed inputs and read off SHAPE properties.

    * prefix-growth steps: for each random base list, walk [] -> [x0] -> [x0,x1] -> ... and record the
      per-step output delta (monotonicity, +1 increment, +elem increment, extremal update).
    * permutation: shuffle a list and check the output is unchanged (order-independence).
    * length ladder: correlate output with list length (does it grow with n?).
    All fractions are over VALID integer-output steps; a step whose oracle output is non-int is skipped.
    """
    up = dn = d1 = de = eu = ed = steps = 0
    perm_ok = perm_tot = 0
    lengths: list[int] = []
    outs: list[int] = []
    single_ok = single_tot = 0

    for _ in range(n_lists):
        L = rng.randint(1, max_len)
        base = tuple(rng.randint(lo, hi) for _ in range(L))
        # prefix walk
        prev_out = oracle(())
        prev_out = prev_out if isinstance(prev_out, int) else None
        for i in range(1, L + 1):
            pref = base[:i]
            o = oracle(pref)
            if not isinstance(o, int):
                prev_out = None
                continue
            if prev_out is not None:
                elem = base[i - 1]
                d = o - prev_out
                steps += 1
                up += (d >= 0)
                dn += (d <= 0)
                d1 += (d == 1)
                de += (d == elem)
                eu += (o == max(prev_out, elem))
                ed += (o == min(prev_out, elem))
            prev_out = o
        # length ladder sample (final output of this list)
        fo = oracle(base)
        if isinstance(fo, int):
            lengths.append(L)
            outs.append(fo)
        # permutation stability
        shuf = list(base)
        rng.shuffle(shuf)
        a, b = oracle(base), oracle(tuple(shuf))
        if isinstance(a, int) and isinstance(b, int):
            perm_tot += 1
            perm_ok += (a == b)
        # singleton
        a1 = base[0]
        so = oracle((a1,))
        if isinstance(so, int):
            single_tot += 1
            single_ok += (so == a1)

    def frac(a: int, b: int) -> float:
        return (a / b) if b else 0.0

    # length correlation, normalised to [0, 1]
    if len(outs) >= 3 and len(set(lengths)) >= 2 and len(set(outs)) >= 2:
        c = float(np.corrcoef(np.asarray(lengths, float), np.asarray(outs, float))[0, 1])
        if not np.isfinite(c):
            c = 0.0
    else:
        c = 0.0
    return {
        "mono_up": frac(up, steps), "mono_down": frac(dn, steps),
        "delta_is_one": frac(d1, steps), "delta_is_elem": frac(de, steps),
        "extremal_up": frac(eu, steps), "extremal_down": frac(ed, steps),
        "perm_invariant": frac(perm_ok, perm_tot), "len_correlation": (c + 1.0) / 2.0,
        "singleton_is_input": frac(single_ok, single_tot),
    }


def feature_dict(spec: Sequence[tuple], oracle: Callable[[tuple], Any], rng: random.Random, *,
                 conflict: bool | None = None, listvar: str = "xs", lo: int = 0, hi: int = 9,
                 max_len: int = 7) -> dict[str, float]:
    """Full labelled structural-feature dict for a wall. `spec` are full-length (env, out) examples;
    `oracle` maps an input tuple to the reference output (used for the behavioural probes); `conflict`
    is the prefix-closed scalar-fold-conflict flag (computed by the caller via `tsig.conflict_from_outer`,
    which needs oracle prefix access). Deterministic given `rng`."""
    feats = _spec_features(spec, listvar)
    feats["scalar_fold_conflict"] = 1.0 if conflict else 0.0
    feats.update(_probe_features(oracle, rng, lo=lo, hi=hi, max_len=max_len))
    return {k: float(feats.get(k, 0.0)) for k in FEATURE_NAMES}


def feature_vector(spec: Sequence[tuple], oracle: Callable[[tuple], Any], rng: random.Random, *,
                   conflict: bool | None = None, listvar: str = "xs", lo: int = 0, hi: int = 9,
                   max_len: int = 7) -> np.ndarray:
    """The recogniser's input: the labelled feature dict as an ordered float vector (len N_FEATURES)."""
    d = feature_dict(spec, oracle, rng, conflict=conflict, listvar=listvar, lo=lo, hi=hi, max_len=max_len)
    return np.asarray([d[k] for k in FEATURE_NAMES], dtype=np.float64)


def fhrr_signature(spec: Sequence[tuple], *, conflict: bool | None = None) -> np.ndarray:
    """The v1 FHRR phasor signature (reused UNCHANGED) — still the ledger's retrieval key. The recogniser
    reads the richer `feature_vector`; the ledger clusters on this bundled 6-axis phasor exactly as v1."""
    return tsig.signature(spec, conflict=conflict)


# ================================================================================================
# H4 v3 — FIX (1): THE SHARPER EXTREMAL-DIRECTION PROBE (the min2-vs-max2 collision fix).
# ------------------------------------------------------------------------------------------------
# v2's direction signal lived in `extremal_up`/`extremal_down`/`singleton_is_input`, which read whether
# the COMPOSITE output ITSELF behaves like a running max / running min. For a COMPUTED family whose output
# is NOT a bare extremum (sum-min, sum-max, max+min) those probes collapse: sum-min and sum-max BOTH look
# like a monotone-growing accumulator, so {add,min2} and {add,max2} collide and the net confidently
# mispredicts the wrong extreme (v2's summin held-out FAIL: rank 16->17, top = {add,max2}).
#
# THE FIX — a MARGINAL-CONTRIBUTION probe. The op `max2` (running MAX) means the MAXIMUM element plays a
# SPECIAL, super-/sub-additive role in the aggregate BEYOND its plain additive contribution; `min2` means
# the MINIMUM element does. We measure exactly that, from I/O alone, by comparing the output's marginal
# sensitivity to the extreme element against a plain MIDDLE element (whose contribution is purely additive
# for every family here):
#     max_role = | E[ d out / d(max elem) ]  -  E[ d out / d(mid elem) ] |
#     min_role = | E[ d out / d(min elem) ]  -  E[ d out / d(mid elem) ] |
# A middle element cancels the additive baseline, so the residual is EXACTLY the extreme's special role.
# Empirically (verified on the four reference oracles): max_role ~= 1 in EVERY family where max2 is present
# (summax, range, maxmin) and ~= 0 where absent (summin); min_role ~= 1 wherever min2 is present (summin,
# range, maxmin) and ~= 0 where absent (summax). Crucially it is COMPOSITION-INVARIANT — max2's signature
# is the SAME value whether it co-occurs with add (summax) or min2 (extent) — which is what lets a detector
# trained on ONE family transfer to a HELD-OUT family it never saw. This is a genuine behavioural probe
# (oracle queried on perturbed inputs), never the answer: for a projection ORDER wall (2nd-max) it reads
# ~0.3 even though its driver is max2, so it is NOT a label oracle — the recogniser still LEARNS role->op.
# ================================================================================================
DIRECTION_FEATURE_NAMES: tuple[str, ...] = (
    "max_role",   # |marginal sensitivity to the MAX element minus a middle element| -> max2-presence
    "min_role",   # |marginal sensitivity to the MIN element minus a middle element| -> min2-presence
)

# The v3 feature vocabulary is a strict SUPERSET of v2's (append-only; v2 indices are unchanged so a v2
# recogniser is byte-for-byte unaffected). Only a v3 recogniser sees the two extra dims.
FEATURE_NAMES_V3: tuple[str, ...] = FEATURE_NAMES + DIRECTION_FEATURE_NAMES
N_FEATURES_V3 = len(FEATURE_NAMES_V3)


def _extremal_marginal_probe(oracle: Callable[[tuple], Any], rng: random.Random, *, lo: int, hi: int,
                             delta: int = 1, n_lists: int = 40) -> dict[str, float]:
    """Marginal-contribution direction probe. For each constructed DISTINCT-valued list (so the max and
    min are UNIQUE and stay the extreme under a small perturbation), query the oracle on three one-element
    perturbations and read the extreme's role RELATIVE to a middle element:
        s_max = (oracle(max += d) - oracle(base)) / d          # d out per unit rise of the MAX element
        s_min = (oracle(min -= d) - oracle(base)) / (-d)       # d out per unit rise of the MIN element
        s_mid = (oracle(mid += d) - oracle(base)) / d          # d out per unit rise of a MIDDLE element
    `max_role`/`min_role` = |mean(s_max - s_mid)| / |mean(s_min - s_mid)|, clipped to [0,1]. The middle
    element cancels the purely-additive baseline, isolating the extreme's special (running-max/min) role.
    Deterministic given `rng`; a wall too narrow to build a 4-distinct list returns the neutral 0.5."""
    ex_max: list[float] = []
    ex_min: list[float] = []
    span = list(range(lo, hi + 1))
    if len(span) < 4:
        return {"max_role": 0.5, "min_role": 0.5}
    tries = 0
    while len(ex_max) < n_lists and tries < n_lists * 12:
        tries += 1
        L = rng.randint(4, min(6, len(span)))
        vals = rng.sample(span, L)                              # distinct -> unique extremes
        xs = tuple(vals)
        mx, mn = max(xs), min(xs)
        if xs.count(mx) != 1 or xs.count(mn) != 1:
            continue
        imax, imin = xs.index(mx), xs.index(mn)
        mids = [i for i in range(L) if i not in (imax, imin)]
        if not mids:
            continue
        imid = rng.choice(mids)
        base = oracle(xs)
        if not isinstance(base, int):
            continue
        up = list(xs); up[imax] = mx + delta
        dn = list(xs); dn[imin] = mn - delta
        md = list(xs); md[imid] = xs[imid] + delta
        o_up, o_dn, o_md = oracle(tuple(up)), oracle(tuple(dn)), oracle(tuple(md))
        if not all(isinstance(o, int) for o in (o_up, o_dn, o_md)):
            continue
        s_max = (o_up - base) / delta
        s_min = (o_dn - base) / (-delta)
        s_mid = (o_md - base) / delta
        ex_max.append(s_max - s_mid)
        ex_min.append(s_min - s_mid)
    if not ex_max:
        return {"max_role": 0.5, "min_role": 0.5}
    mr = min(1.0, abs(sum(ex_max) / len(ex_max)))
    nr = min(1.0, abs(sum(ex_min) / len(ex_min)))
    return {"max_role": float(mr), "min_role": float(nr)}


def feature_dict_v3(spec: Sequence[tuple], oracle: Callable[[tuple], Any], rng: random.Random, *,
                    conflict: bool | None = None, listvar: str = "xs", lo: int = 0, hi: int = 9,
                    max_len: int = 7) -> dict[str, float]:
    """v3 labelled feature dict: the full v2 `feature_dict` PLUS the two extremal-direction features. The
    direction probe uses an INDEPENDENT seeded rng stream (derived from `rng`) so the v2 features are
    byte-for-byte identical to `feature_dict` given the same `rng`."""
    d = feature_dict(spec, oracle, rng, conflict=conflict, listvar=listvar, lo=lo, hi=hi, max_len=max_len)
    dir_rng = random.Random((rng.randint(0, 2 ** 31 - 1)) ^ 0x0D18EC)
    d.update(_extremal_marginal_probe(oracle, dir_rng, lo=lo, hi=hi))
    return {k: float(d.get(k, 0.0)) for k in FEATURE_NAMES_V3}


def feature_vector_v3(spec: Sequence[tuple], oracle: Callable[[tuple], Any], rng: random.Random, *,
                      conflict: bool | None = None, listvar: str = "xs", lo: int = 0, hi: int = 9,
                      max_len: int = 7) -> np.ndarray:
    """The v3 recogniser's input: the v3 feature dict as an ordered float vector (len N_FEATURES_V3)."""
    d = feature_dict_v3(spec, oracle, rng, conflict=conflict, listvar=listvar, lo=lo, hi=hi, max_len=max_len)
    return np.asarray([d[k] for k in FEATURE_NAMES_V3], dtype=np.float64)
