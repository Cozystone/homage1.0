# -*- coding: utf-8 -*-
"""H4 v3 (the two named fixes over v2) — fast unit tests locking the invariants.

The heavy cross-family signal-4 + held-out-family transfer measurement lives in
`cross_family_v3.signal4_cross_family_v3` / `cross_family_v3.heldout_family_transfer_v3` (run in
scratchpad). These fast tests lock: (a) the v3 feature vocab is APPEND-ONLY (v2 indices byte-identical),
(b) the extremal-direction probe (fix 1) cleanly separates min2 from max2 and is composition-invariant,
(c) it is a behavioural probe, NOT an answer/label leak, (d) the co-occurrence head (fix 2) is under the
N3 budget and LEARNS to lock {max2,min2} as a set (independent sigmoids cannot), (e) the structured head
stays COMPOSITIONAL — it can score an aux-set never seen in training (held-out transfer is reachable),
(f) v3 crosses every family with propose-verify integrity, (g) No-LLM / no exec-eval and the recogniser
never sees the answer."""
from __future__ import annotations

import random

import numpy as np

from packages.evolution import open_domain as od
from packages.self_acceleration import structural_features as sf
from packages.self_acceleration import recognizer as R
from packages.self_acceleration import cross_family_v3 as cf3
from packages.self_acceleration import cross_family_curriculum as cur
from packages.self_acceleration import trace_signature as tsig


def _dir_feats(name):
    w = cur.by_name(name)
    rng = random.Random(1)
    spec = w.samples(16, rng); outer = w.outer(10, rng)
    conf = tsig.conflict_from_outer(outer, w.listvar)
    prng = random.Random(hash((w.name, "probe")) & 0xFFFFFFFF)
    return sf.feature_dict_v3(spec, w.oracle, prng, conflict=conf, lo=w.lo, hi=w.hi, max_len=w.max_len)


# --- (a) the v3 feature vocabulary is APPEND-ONLY: v2 indices are byte-identical -------------------
def test_v3_features_are_append_only():
    assert sf.N_FEATURES_V3 == sf.N_FEATURES + 2
    assert sf.FEATURE_NAMES_V3[:sf.N_FEATURES] == sf.FEATURE_NAMES     # v2 dims unchanged in place
    assert sf.FEATURE_NAMES_V3[sf.N_FEATURES:] == ("max_role", "min_role")
    # v2 feature_vector is byte-for-byte the prefix of feature_vector_v3 given the same rng
    w = cur.by_name("range"); rng = random.Random(5)
    spec = w.samples(16, rng); outer = w.outer(10, rng)
    conf = tsig.conflict_from_outer(outer, w.listvar)
    v2 = sf.feature_vector(spec, w.oracle, random.Random(9), conflict=conf, lo=w.lo, hi=w.hi, max_len=w.max_len)
    v3 = sf.feature_vector_v3(spec, w.oracle, random.Random(9), conflict=conf, lo=w.lo, hi=w.hi, max_len=w.max_len)
    assert np.allclose(v2, v3[:sf.N_FEATURES])


# --- (b) fix 1: direction features separate min2 vs max2, COMPOSITION-INVARIANTLY ----------------
def test_direction_features_separate_min2_max2():
    d = {n: _dir_feats(n) for n in ("range", "maxmin_sum", "sum_minus_min", "sum_minus_max", "second_max")}
    # summin ({add,min2}) and summax ({add,max2}) — which COLLIDED in v2 — are now clearly separated:
    assert d["sum_minus_min"]["max_role"] < 0.25 and d["sum_minus_min"]["min_role"] > 0.75   # min2, NOT max2
    assert d["sum_minus_max"]["min_role"] < 0.25 and d["sum_minus_max"]["max_role"] > 0.75   # max2, NOT min2
    # composition-INVARIANCE: max2's signature is high wherever max2 is present (summax, range, maxmin),
    # low where absent (summin) — the SAME value across families, which is what lets it transfer.
    assert d["range"]["max_role"] > 0.75 and d["maxmin_sum"]["max_role"] > 0.75
    assert d["range"]["min_role"] > 0.75 and d["maxmin_sum"]["min_role"] > 0.75


# --- (c) the direction probe is a BEHAVIOURAL probe, NOT an answer/label leak ---------------------
def test_direction_probe_is_not_a_label_leak():
    # the order family's true aux is max2, yet its max_role reads LOW (perturbing a 2nd-max wall's unique
    # max leaves the 2nd-max unchanged) — so the feature is NOT an oracle for the aux label; the recogniser
    # must still LEARN role->op. A leak would read max_role~1 for every max2 wall including order.
    d = _dir_feats("second_max")
    assert d["max_role"] < 0.6            # NOT a clean 1.0 -> not a label oracle


# --- (d) fix 2: the co-occurrence head is TINY and LOCKS {max2,min2} as a set ---------------------
def test_cooccurrence_head_budget_and_locks_set():
    rec = R.MoveRecognizerV3(n_features=sf.N_FEATURES_V3, seed=7)
    n = rec.n_params()
    assert n < 25_000_000 and n < 5000                     # N3 budget; a few hundred params
    assert n == R.MoveRecognizer(n_features=sf.N_FEATURES_V3, seed=7).n_params() + len(rec._pairs)  # +pairwise
    # a range-like feature (both extremes special) -> the head locks the {max2,min2} SET, not either alone
    f = np.zeros(sf.N_FEATURES_V3)
    f[sf.FEATURE_NAMES_V3.index("max_role")] = 1.0
    f[sf.FEATURE_NAMES_V3.index("min_role")] = 1.0
    f[sf.FEATURE_NAMES_V3.index("out_exceeds_max")] = 1.0
    f2 = np.zeros(sf.N_FEATURES_V3)
    f2[sf.FEATURE_NAMES_V3.index("min_role")] = 1.0
    f2[sf.FEATURE_NAMES_V3.index("delta_is_elem")] = 1.0
    ex = [R.RecipeExample(f, R.MoveComposition("computed_projection", aux_ops=("max2", "min2")), "range"),
          R.RecipeExample(f2, R.MoveComposition("computed_projection", aux_ops=("add", "min2")), "summin")]
    info = rec.fit(ex, epochs=500)
    assert info["trained"]
    pf, ps = rec.predict_sets(f)
    sets = R.aux_set_space()
    best = max(zip(sets, ps), key=lambda t: t[1])[0]
    assert frozenset(best) == frozenset(("max2", "min2"))  # co-occurrence locked


# --- (e) the structured head stays COMPOSITIONAL: an UNSEEN aux-set is still reachable -------------
def test_structured_head_is_compositional_unseen_set_reachable():
    # train ONLY on {add,max2} and {max2,min2}; the set {add,min2} is NEVER a training label.
    rec = R.MoveRecognizerV3(n_features=sf.N_FEATURES_V3, seed=7)
    fa = np.zeros(sf.N_FEATURES_V3); fa[sf.FEATURE_NAMES_V3.index("max_role")] = 1.0
    fa[sf.FEATURE_NAMES_V3.index("delta_is_elem")] = 1.0
    fb = np.zeros(sf.N_FEATURES_V3); fb[sf.FEATURE_NAMES_V3.index("max_role")] = 1.0
    fb[sf.FEATURE_NAMES_V3.index("min_role")] = 1.0
    ex = [R.RecipeExample(fa, R.MoveComposition("computed_projection", aux_ops=("add", "max2")), "summax"),
          R.RecipeExample(fb, R.MoveComposition("computed_projection", aux_ops=("max2", "min2")), "range")]
    rec.fit(ex, epochs=400)
    # a feature with add-signal + min2-signal: the NEVER-TRAINED set {add,min2} must be REACHABLE (nonzero,
    # shared unary+pairwise energy) — a free per-class softmax would pin it at ~0. We only require it is a
    # live candidate the compositional head can assemble, not that it wins here.
    fq = np.zeros(sf.N_FEATURES_V3); fq[sf.FEATURE_NAMES_V3.index("min_role")] = 1.0
    fq[sf.FEATURE_NAMES_V3.index("delta_is_elem")] = 1.0
    _, ps = rec.predict_sets(fq)
    sets = R.aux_set_space()
    p_addmin = float(ps[[frozenset(s) for s in sets].index(frozenset(("add", "min2")))])
    assert p_addmin > 1e-4                                  # unseen set is reachable (compositional)


# --- (f) v3 crosses every family with PROPOSE-VERIFY integrity ------------------------------------
def test_v3_full_crosses_all_families():
    run = cf3.run_cross_family_v3("v3", variant="full", seed=7)
    assert run["walls_crossed"] == run["walls_total"]
    for r in run["results"]:
        assert r.crossed and r.composition


def test_v3_propose_verify_rejects_wrong_composition():
    w = cur.by_name("sum_minus_min")
    rng = random.Random(3)
    outer = w.outer(10, rng); verify = w.samples(14, rng); ho = w.samples(30, rng)
    fsig = sf.fhrr_signature(w.samples(16, rng), conflict=True)
    st = cf3.fresh_state()
    wrong = R.MoveComposition("computed_projection", aux_ops=("max2", "add"))   # summax set on a summin wall
    r = cf3._expand_and_synthesize(wrong, w, outer, verify, st, fsig, use_ledger=False)
    assert not (r.get("solved") and od.fitness(r.get("tree"), ho) >= 1.0)       # never a fabricated cross
    right = R.MoveComposition("computed_projection", aux_ops=("add", "min2"))
    r2 = cf3._expand_and_synthesize(right, w, outer, verify, st, fsig, use_ledger=False)
    assert r2.get("solved") and od.fitness(r2["tree"], ho) >= 1.0               # the true set does cross


# --- (g) No-LLM / no exec-eval, recogniser input is features only --------------------------------
def test_v3_no_exec_or_eval():
    import packages.self_acceleration.cross_family_v3 as m3
    for m in (sf, R, m3):
        src = open(m.__file__, encoding="utf-8").read()
        assert "exec(" not in src and "eval(" not in src, m.__file__


# --- (h) v3.1 SIGNATURE-COUPLED — genuine held-out transfer (the deliverable) ---------------------
def test_coupled_recognizer_budget_and_shared_presence():
    rec = R.SignatureCoupledRecognizer(
        n_features=sf.N_FEATURES_V3, seed=7,
        max_role_idx=sf.FEATURE_NAMES_V3.index("max_role"),
        min_role_idx=sf.FEATURE_NAMES_V3.index("min_role"),
        add_sig_idx=sf.FEATURE_NAMES_V3.index("delta_is_elem"))
    assert rec.n_params() < 25_000_000 and rec.n_params() < 5000        # N3 budget (+2 shared g params)
    assert rec.n_params() == R.MoveRecognizerV3(n_features=sf.N_FEATURES_V3, seed=7).n_params() + 2


def test_coupled_heldout_transfer_summin_and_extent():
    """The make-or-break: on the REAL harness (synthesis + re-execution gate), the coupled recogniser
    predicts a NEVER-TRAINED family's true composition at rank ~0 and crosses far cheaper than blind. This
    exercises the whole pipeline (ledger recording + symmetric presence + structural routing), so it also
    guards the two bootstrapping fixes (prior anchors; family-primary sort)."""
    import packages.self_acceleration.cross_family_v3 as cf3
    for fam in ("summin", "extent"):
        t = cf3.heldout_family_transfer_v3(fam, variant="coupled", seed=7)
        s = t["summary"]
        assert s["trained_mean_rank_of_true"] is not None
        assert s["trained_mean_rank_of_true"] <= 1.0, (fam, s["trained_mean_rank_of_true"])   # near rank 0
        assert all(r["crossed"] for r in t["trained"])                 # verified crossings (0 fabrication)
        # structure, not memorisation: trained (on 3 OTHER families) crosses the cold 4th cheaper than blind
        assert s["trained_total_work"] <= s["blind_total_work"], (fam, s["trained_total_work"], s["blind_total_work"])
