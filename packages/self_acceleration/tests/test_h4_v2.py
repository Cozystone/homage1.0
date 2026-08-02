# -*- coding: utf-8 -*-
"""H4 v2 (learned cross-family recogniser) — fast unit tests locking the invariants.

The heavy cross-family signal-4 measurement + the held-out-family transfer acid test live in
scratchpad/h4v2/run_cross_family.py and `cross_family.signal4_cross_family` /
`cross_family.heldout_family_transfer`. These fast tests lock: (a) N3 param budget, (b) the recogniser is
genuinely LEARNED (training moves predictions toward ledger labels), (c) the composition space composes
moves the v1 fixed set cannot express, (d) structural features are autonomous + discriminative, (e) the
order family still COMPOUNDS via analogy at zero synth-evals (v1 preserved), (f) PROPOSE-VERIFY integrity
(a wrong composition never yields a fabricated cross), (g) v2 crosses every family, and (h) No-LLM /
no-exec + the recogniser never sees the answer."""
from __future__ import annotations

import random

import numpy as np

from packages.evolution import open_domain as od
from packages.self_acceleration import structural_features as sf
from packages.self_acceleration import recognizer as R
from packages.self_acceleration import cross_family as cf
from packages.self_acceleration import cross_family_curriculum as cur


# --- (a) N3 neuro-budget: the single model is far under 25M params -------------------------------
def test_recognizer_param_budget():
    rec = R.MoveRecognizer(n_features=sf.N_FEATURES, seed=7)
    n = rec.n_params()
    assert n < 25_000_000, n
    assert n < 5000                       # it is TINY — a few hundred params, CPU-fine


# --- (c) the composition space COMPOSES moves the v1 fixed {range, sum} set cannot express -------
def test_composition_space_composes():
    comps = R.all_compositions()
    labels = {c.label for c in comps}
    # projection GROW at several depths + computed aux-set compositions across the LIFT vocabulary.
    # (labels list ops in AUX_OPS order: max2,min2,add,mul,cnt — so summin's set reads {min2,add})
    assert any(c.family == "projection_chain" for c in comps)
    assert "computed_projection({max2,min2})" in labels     # extent (v1 has this via {range})
    assert "computed_projection({min2,add})" in labels      # summin — v1's fixed set CANNOT express
    assert "computed_projection({max2,add})" in labels      # summax — v1's fixed set CANNOT express
    assert "computed_projection({add,cnt})" in labels       # a composition never in any curriculum wall
    # the aux-set is order-agnostic for matching (frozenset), only the label string is ordered
    assert frozenset(("add", "min2")) == frozenset(("min2", "add"))


# --- (b) the recogniser is LEARNED, not hardcoded: fit moves predictions toward the labels -------
def test_recognizer_is_learned():
    # synthetic ledger: a computed {add,min2} wall-feature vs a projection {max2} wall-feature
    f_comp = np.zeros(sf.N_FEATURES); f_comp[sf.FEATURE_NAMES.index("out_exceeds_max")] = 1.0
    f_proj = np.zeros(sf.N_FEATURES); f_proj[sf.FEATURE_NAMES.index("out_is_member")] = 1.0
    ex = [
        R.RecipeExample(f_comp, R.MoveComposition("computed_projection", aux_ops=("add", "min2")), "w1"),
        R.RecipeExample(f_proj, R.MoveComposition("projection_chain", depth=2), "w2"),
    ]
    rec = R.MoveRecognizer(n_features=sf.N_FEATURES, seed=7)
    before_pf, before_pa = rec.predict(f_comp)
    W1_before = rec.W1.copy()
    info = rec.fit(ex, epochs=500)
    assert info["trained"] and info["n"] == 2
    assert not np.allclose(W1_before, rec.W1)                 # weights actually changed
    after_pf, after_pa = rec.predict(f_comp)
    # trained: the computed-family + {add,min2} aux prediction rose for the computed feature vector
    assert after_pf[R.FAMILIES.index("computed_projection")] > before_pf[R.FAMILIES.index("computed_projection")]
    assert after_pa[R.AUX_OPS.index("add")] > 0.5 and after_pa[R.AUX_OPS.index("min2")] > 0.5
    assert after_pa[R.AUX_OPS.index("max2")] < 0.5           # NOT the ops it never saw for this feature


# --- (d) features are AUTONOMOUS (from I/O + oracle, never the answer) + discriminative ----------
def test_features_autonomous_and_discriminative():
    def feats(name):
        w = cur.by_name(name)
        rng = random.Random(1)
        spec = w.samples(16, rng); outer = w.outer(10, rng)
        from packages.self_acceleration import trace_signature as tsig
        conf = tsig.conflict_from_outer(outer, w.listvar)
        prng = random.Random(2)
        return sf.feature_dict(spec, w.oracle, prng, conflict=conf, lo=w.lo, hi=w.hi, max_len=w.max_len)
    rng_f, summin_f = feats("range"), feats("sum_minus_min")
    # range stays bounded by max; sum-min routinely exceeds max -> a genuine structural discriminator
    assert rng_f["out_exceeds_max"] < 0.2 and summin_f["out_exceeds_max"] > 0.5
    # sum-based walls carry the 'delta == element' (running-sum) fingerprint far more than range
    assert summin_f["delta_is_elem"] > rng_f["delta_is_elem"]


# --- (e) the order family still COMPOUNDS via analogy at zero synth-evals (v1 preserved) ---------
def test_order_family_compounds_zero_search():
    order = cur.walls_of("order")
    run = cf.run_cross_family("v2", walls=order, seed=7)
    by = {r.name: r for r in run["results"]}
    assert by["second_max"].crossed and by["second_max"].via == "oe"       # genuine invention
    for n in ("third_max", "fourth_max", "fifth_max"):
        assert by[n].crossed and by[n].via == "analogy" and by[n].synth_evals == 0   # zero-search compound


# --- (f) PROPOSE-VERIFY integrity: a WRONG composition never yields a fabricated cross -----------
def test_propose_verify_rejects_wrong_composition():
    w = cur.by_name("range")
    rng = random.Random(3)
    outer = w.outer(10, rng); verify = w.samples(14, rng); ho = w.samples(30, rng)
    from packages.self_acceleration import structural_features as _sf
    fsig = _sf.fhrr_signature(w.samples(16, rng), conflict=True)
    st = cf.fresh_state()
    # a deliberately WRONG aux-set for range (count): the synthesiser cannot fit it, and even if OE
    # found a spurious pi on `verify`, the holdout re-execution gate would score < 1.0.
    wrong = R.MoveComposition("computed_projection", aux_ops=("cnt",))
    r = cf._expand_and_synthesize(wrong, w, outer, verify, st, fsig, use_ledger=False)
    assert not (r.get("solved") and od.fitness(r.get("tree"), ho) >= 1.0)   # never a verified cross
    # and the RIGHT aux-set does cross AND re-executes on holdout (the honest positive)
    right = R.MoveComposition("computed_projection", aux_ops=("max2", "min2"))
    r2 = cf._expand_and_synthesize(right, w, outer, verify, st, fsig, use_ledger=False)
    assert r2.get("solved") and od.fitness(r2["tree"], ho) >= 1.0


# --- (g) v2 crosses every family (the recogniser proposes a VERIFIED composition for each) -------
def test_v2_crosses_all_families():
    run = cf.run_cross_family("v2", seed=7)
    assert run["walls_crossed"] == run["walls_total"]
    # every cross is verified (crossed True) and carries a concrete composition label
    for r in run["results"]:
        assert r.crossed and r.composition


# --- (h) No-LLM / no exec-eval, and the recogniser input is features only (never the answer) -----
def test_no_exec_or_eval_in_v2_modules():
    import packages.self_acceleration.structural_features as m1
    import packages.self_acceleration.recognizer as m2
    import packages.self_acceleration.cross_family as m3
    import packages.self_acceleration.cross_family_curriculum as m4
    for m in (m1, m2, m3, m4):
        src = open(m.__file__, encoding="utf-8").read()
        assert "exec(" not in src and "eval(" not in src, m.__file__


def test_recognizer_input_is_features_only():
    # the recogniser's public surface takes a feature vector / RecipeExample(features, composition) —
    # never a wall, a reference function, or a true_aux label. (Autonomy: it learns feature->move.)
    import inspect
    sig = inspect.signature(R.MoveRecognizer.fit)
    assert list(sig.parameters)[1] == "examples"
    ex = R.RecipeExample(np.zeros(sf.N_FEATURES), R.MoveComposition("projection_chain", depth=2))
    assert hasattr(ex, "features") and hasattr(ex, "composition")
    assert not any(k in R.RecipeExample.__dataclass_fields__ for k in ("ref", "true_aux", "answer"))
