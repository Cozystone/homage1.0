# -*- coding: utf-8 -*-
"""H4 v3 — the CROSS-FAMILY loop + signal-4 harness, wired to the TWO v3 fixes (additive over v2).

WHAT CHANGED FROM v2 (and ONLY this)
------------------------------------
A byte-for-byte re-run of v2's `cross_family` protocol — SAME curriculum (`cross_family_curriculum`,
reference-only, never seen by the synthesiser), SAME baselines, SAME held-out splits, SAME budgets, SAME
seeds, SAME propose-verify re-execution gate (`od.fitness(prog, holdout) >= 1.0` — zero fabrication) — with
exactly the two v3 organs swapped in, selectable by `variant` so each fix is measurable in isolation:

  * FIX 1 (features): `structural_features.feature_vector_v3` — v2's 17 features PLUS the two
    extremal-direction features (`max_role`, `min_role`) that cleanly separate min2 from max2. The
    make-or-break for the summin held-out family ({add,min2}), which v2 could not tell from summax
    ({add,max2}).
  * FIX 2 (head): `recognizer.MoveRecognizerV3` — v2's independent-sigmoid aux head REPLACED by a
    structured co-occurrence head (softmax over the aux-SET space + a learnable pairwise term), so
    {max2,min2} co-occurrence is learnable. The make-or-break for the extent held-out family, ranked 5.5
    by v2 because independent sigmoids cannot model op co-occurrence.

variant:
  * "fix1"  — v3 features + v2's INDEPENDENT-sigmoid head (isolates fix 1's marginal contribution).
  * "full"  — v3 features + the co-occurrence head (fix 1 + fix 2 together).

Everything else — the synthesiser (`scheme_space`), the projection-chain analogy compounding, the v1
proposer baseline, the work accounting — is REUSED UNCHANGED from `cross_family`. Entry points mirror v2
one-for-one so the numbers are directly comparable:
  * `signal4_cross_family_v3(seed, variant)`          <-> v2 `cross_family.signal4_cross_family(seed)`
  * `heldout_family_transfer_v3(family, seed, variant)`<-> v2 `cross_family.heldout_family_transfer(family)`

No-LLM, numpy + stdlib, deterministic.
"""
from __future__ import annotations

import random
from typing import Any

from packages.evolution import open_domain as od
from packages.self_acceleration import trace_signature as tsig
from packages.self_acceleration import structural_features as sf
from packages.self_acceleration import cross_family as cf
from packages.self_acceleration import h4 as _h4
from packages.self_acceleration.recognizer import (
    MoveRecognizer, MoveRecognizerV3, SignatureCoupledRecognizer, MoveComposition, RecipeExample,
    all_compositions, AUX_OPS, FAMILIES as _FAMS,
)
from packages.self_acceleration import cross_family_curriculum as cur

# reuse v2's bounded OE budgets + result type + reachability expansion + curves VERBATIM (no second impl)
WallResultV2 = cf.WallResultV2
fresh_state = cf.fresh_state
_expand_and_synthesize = cf._expand_and_synthesize
_proj_resonance = cf._proj_resonance
run_v1_proposer = cf.run_v1_proposer


def _make_recognizer(variant: str, *, n_features: int, hidden: int = 24, seed: int = 7):
    if variant == "coupled":
        return SignatureCoupledRecognizer(
            n_features=n_features, hidden=hidden, seed=seed,
            max_role_idx=sf.FEATURE_NAMES_V3.index("max_role"),
            min_role_idx=sf.FEATURE_NAMES_V3.index("min_role"),
            add_sig_idx=sf.FEATURE_NAMES_V3.index("delta_is_elem"))
    if variant == "full":
        return MoveRecognizerV3(n_features=n_features, hidden=hidden, seed=seed)
    return MoveRecognizer(n_features=n_features, hidden=hidden, seed=seed)   # "fix1": v2's head


# ============================================================================================
# HYBRID RANKING (v3) — IDENTICAL structure to v2's `rank_for_wall` in EVERY variant: projection DEPTH
# ordering is v1's reused resonance ranker (not the learned differential); the LEARNED differential is
# exactly the computed aux-SET score. For "fix1" that score is v2's Bernoulli product of independent
# sigmoids (`cf.rank_for_wall`); for "full" it is the structured co-occurrence head's SET probability.
# ============================================================================================
def rank_for_wall_cooc(recognizer: MoveRecognizerV3, feats, spec: list) -> list[tuple[MoveComposition, float]]:
    pf, ps = recognizer.predict_sets(feats)
    g_proj = float(pf[_FAMS.index("projection_chain")])
    g_comp = float(pf[_FAMS.index("computed_projection")])
    comps = all_compositions()
    res = _proj_resonance(spec)
    order_index = {c.label: i for i, c in enumerate(comps)}
    scored = []
    for c in comps:
        if c.family == "projection_chain":
            s = g_proj * res.get(c.label, 0.0)
        else:
            k = recognizer._set_index.get(frozenset(c.aux_ops))
            s = g_comp * float(ps[k]) if k is not None else 0.0
        scored.append((c, s))
    scored.sort(key=lambda t: (-t[1], order_index[t[0].label]))
    return scored


def rank_for_wall_coupled(recognizer: SignatureCoupledRecognizer, feats, spec: list
                          ) -> list[tuple[MoveComposition, float]]:
    """v3.1 ranker: family gate is STRUCTURAL (computed-ness from clean aggregate signatures); the computed
    aux-set score is a Bernoulli product over the SYMMETRIC extremal presences + the net's add/mul/cnt;
    projection depth is v1's reused resonance ranker (unchanged in every arm)."""
    g_comp, p = recognizer.coupled_scores(feats)
    g_proj = 1.0 - g_comp
    comps = all_compositions()
    res = _proj_resonance(spec)
    order_index = {c.label: i for i, c in enumerate(comps)}
    pred_computed = g_comp >= 0.5                     # the structurally-routed family
    scored = []
    for c in comps:
        if c.family == "projection_chain":
            s = g_proj * res.get(c.label, 0.0)
        else:
            inset = set(c.aux_ops)
            lik = 1.0
            for op in AUX_OPS:
                lik *= p[op] if op in inset else (1.0 - p[op])
            s = g_comp * lik
        scored.append((c, s))
    # PRIMARY key = the routed family, so a computed wall EXHAUSTS its aux-sets before falling through to a
    # projection (verification still gates each candidate). Without this, a computed set whose likelihood is
    # ~0 because one op is still cold (e.g. the FIRST add wall, add unlearned) ties at 0 with the projections
    # and loses the Occam tiebreak — a valid-but-different projection then crosses first and the loop never
    # records the computed recipe, starving the op of its training example (the cold-op bootstrapping trap).
    def _key(item):
        c, s = item
        fam_pref = 0 if ((c.family == "computed_projection") == pred_computed) else 1
        return (fam_pref, -s, order_index[c.label])
    scored.sort(key=_key)
    return scored


def _rank(variant: str, recognizer, feats, spec):
    if variant == "coupled":
        return rank_for_wall_coupled(recognizer, feats, spec)
    if variant == "full":
        return rank_for_wall_cooc(recognizer, feats, spec)
    return cf.rank_for_wall(recognizer, feats, spec)          # "fix1" reuses v2's ranker verbatim


# ============================================================================================
# CROSS ONE WALL (v3) — mirrors v2 `cross_wall_v2`; only the feature vector (v3) and the ranker (variant)
# differ. Synthesis, verification, promotion, recipe recording are v2 machinery, unchanged.
# ============================================================================================
def cross_wall_v3(wall, state: dict, recognizer, rng: random.Random, *, variant: str = "full",
                  invent: bool = True, use_ledger: bool = True, record: bool = True,
                  n_outer: int = 10, n_verify: int = 14, n_holdout: int = 40) -> WallResultV2:
    listvar = wall.listvar
    spec = wall.samples(16, rng)
    outer = wall.outer(n_outer, rng)
    verify = wall.samples(n_verify, rng)
    holdout = wall.samples(n_holdout, rng)

    conflict = tsig.conflict_from_outer(outer, listvar)
    probe_rng = random.Random(hash((wall.name, "probe")) & 0xFFFFFFFF)
    feats = sf.feature_vector_v3(spec, wall.oracle, probe_rng, conflict=conflict, listvar=listvar,
                                 lo=wall.lo, hi=wall.hi, max_len=wall.max_len)
    fhrr_sig = sf.fhrr_signature(spec, conflict=conflict)

    ranked = _rank(variant, recognizer, feats, spec)

    synth_evals = verify_execs = tried = 0
    for pos, (comp, _score) in enumerate(ranked):
        r = _expand_and_synthesize(comp, wall, outer, verify, state, fhrr_sig, use_ledger)
        synth_evals += r.get("synth_evals", 0)
        verify_execs += r.get("verify_execs", 0)
        if r.get("via") == "unreachable":
            continue
        tried += 1
        if not r.get("solved"):
            continue
        ho_fit = od.fitness(r["tree"], holdout)
        verify_execs += len(holdout)
        if ho_fit < 1.0:
            continue
        reused = (r.get("via") == "analogy")
        if invent and comp.family == "projection_chain" and r.get("out_step_template") is not None:
            _h4._promote(state, r["out_step_template"], wall.name)
            state["ledger"].add(fhrr_sig, {"family": "projection_chain", "depth": r["k"],
                                           "out_step_template": _h4._to_json(r["out_step_template"])},
                                wall.name)
        elif invent and comp.family == "computed_projection":
            state["ledger"].add(fhrr_sig, {"family": "computed_projection", "depth": r.get("k", 0),
                                           "aux": list(comp.aux_ops), "out_step_template": None}, wall.name)
        if record:
            state["recipes"].append(RecipeExample(features=feats, composition=comp, wall=wall.name,
                                                  family=wall.family))
        return WallResultV2(wall.name, wall.family, crossed=True, via=r.get("via", ""),
                            composition=comp.label, synth_evals=synth_evals, verify_execs=verify_execs,
                            candidates_tried=tried, rank_of_winner=pos, reused_analogy=reused,
                            program=r.get("program", ""))

    return WallResultV2(wall.name, wall.family, crossed=False, synth_evals=synth_evals,
                        verify_execs=verify_execs, candidates_tried=tried)


# ============================================================================================
# RUN THE CURRICULUM under one recogniser mode (v3)
# ============================================================================================
def run_cross_family_v3(mode: str, *, variant: str = "full", walls=None, seed: int = 7, hidden: int = 24,
                        epochs: int = 400) -> dict[str, Any]:
    """mode in {"v3", "frozen"}: "v3" retrains the recogniser on the accumulating ledger before each wall
    (flywheel); "frozen" never trains (random-init net = the no-learning / blind-Occam control)."""
    walls = walls if walls is not None else cur.all_walls()
    state = fresh_state()
    rng = random.Random(seed)
    recognizer = _make_recognizer(variant, n_features=sf.N_FEATURES_V3, hidden=hidden, seed=seed)
    results: list[WallResultV2] = []
    train_log: list[dict] = []
    for w in walls:
        if mode == "v3" and state["recipes"]:
            info = recognizer.fit(state["recipes"], epochs=epochs)
            train_log.append({"before_wall": w.name, "n_recipes": info["n"]})
        results.append(cross_wall_v3(w, state, recognizer, rng, variant=variant))
    crossed = [r for r in results if r.crossed]
    return {"mode": mode, "variant": variant, "seed": seed, "results": results,
            "walls_crossed": len(crossed), "walls_total": len(walls),
            "final_basis_size": len(state["basis"]), "invented_templates": len(state["invented_sources"]),
            "ledger_size": len(state["ledger"]), "n_params": recognizer.n_params(),
            "recognizer": recognizer, "state": state, "train_log": train_log}


# ============================================================================================
# SIGNAL 4 (v3) — the sealed cross-family measurement (mirrors v2 signal4_cross_family)
# ============================================================================================
def signal4_cross_family_v3(seed: int = 7, *, variant: str = "full") -> dict[str, Any]:
    v3 = run_cross_family_v3("v3", variant=variant, seed=seed)
    frozen = run_cross_family_v3("frozen", variant=variant, seed=seed)
    v1 = run_v1_proposer(seed=seed)
    return {
        "seed": seed,
        "variant": variant,
        "n_params": v3["n_params"],
        "walls_crossed": {"v3_recognizer": v3["walls_crossed"], "frozen_no_recognizer": frozen["walls_crossed"],
                          "v1_proposer": v1["walls_crossed"], "total": v3["walls_total"]},
        "work_curve": {"v3_recognizer": cf._work_curve(v3), "frozen_no_recognizer": cf._work_curve(frozen)},
        "first_wall_work": {"v3_recognizer": cf._first_wall_work(v3),
                            "frozen_no_recognizer": cf._first_wall_work(frozen)},
        "runs": {"v3_recognizer": v3, "frozen_no_recognizer": frozen, "v1_proposer": v1},
    }


# ============================================================================================
# HELD-OUT FAMILY TRANSFER (v3) — the acid test (structure vs memorisation), mirrors v2 exactly.
# ============================================================================================
def _rank_of_true_auxset_v3(variant: str, recognizer, feats, spec, wall) -> dict[str, Any]:
    ranked = _rank(variant, recognizer, feats, spec)
    want_aux = frozenset(wall.true_aux)
    want_fam = wall.true_family
    for pos, (comp, score) in enumerate(ranked):
        same_fam = (comp.family == want_fam)
        same_aux = (frozenset(comp.aux_ops) == want_aux) if comp.family == "computed_projection" else True
        if same_fam and same_aux:
            return {"rank_of_true": pos, "score": round(float(score), 6), "top": ranked[0][0].label}
    return {"rank_of_true": -1, "score": 0.0, "top": ranked[0][0].label}


def heldout_family_transfer_v3(holdout: str, *, variant: str = "full", seed: int = 7,
                               epochs: int = 600) -> dict[str, Any]:
    """Train the recogniser on every family EXCEPT `holdout`, freeze it, face the held-out family cold.
    IDENTICAL protocol to v2 `heldout_family_transfer` — only the features (v3) + head (variant) differ."""
    train_families = [f for f in cur.FAMILY_ORDER if f != holdout]
    train_walls = [w for f in train_families for w in cur.walls_of(f)]
    holdout_walls = cur.walls_of(holdout)

    state = fresh_state()
    rng = random.Random(seed)
    trained = _make_recognizer(variant, n_features=sf.N_FEATURES_V3, seed=seed)
    for w in train_walls:
        if state["recipes"]:
            trained.fit(state["recipes"], epochs=epochs)
        cross_wall_v3(w, state, trained, rng, variant=variant)
    trained.fit(state["recipes"], epochs=epochs)

    untrained = _make_recognizer(variant, n_features=sf.N_FEATURES_V3, seed=seed)   # the blind control

    def face(recog):
        st = fresh_state()
        r2 = random.Random(seed + 1)
        rows = []
        for w in holdout_walls:
            spec = w.samples(16, r2)
            outer = w.outer(10, r2)
            conflict = tsig.conflict_from_outer(outer, w.listvar)
            prng = random.Random(hash((w.name, "probe")) & 0xFFFFFFFF)
            feats = sf.feature_vector_v3(spec, w.oracle, prng, conflict=conflict, listvar=w.listvar,
                                         lo=w.lo, hi=w.hi, max_len=w.max_len)
            pred = _rank_of_true_auxset_v3(variant, recog, feats, spec, w)
            res = cross_wall_v3(w, st, recog, r2, variant=variant, invent=True, use_ledger=True,
                                record=False)
            rows.append({"wall": w.name, "true_aux": list(w.true_aux), **pred,
                         "total_work": res.total_work, "rank_of_winner": res.rank_of_winner,
                         "candidates_tried": res.candidates_tried, "crossed": res.crossed,
                         "via": res.via, "won_with": res.composition})
        return rows

    trained_rows = face(trained)
    blind_rows = face(untrained)

    def agg(rows, key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and r[key] >= 0]
        return sum(vals) / len(vals) if vals else None

    return {
        "holdout_family": holdout,
        "variant": variant,
        "trained_on": train_families,
        "n_train_recipes": len(state["recipes"]),
        "trained": trained_rows,
        "blind": blind_rows,
        "summary": {
            "trained_mean_rank_of_true": agg(trained_rows, "rank_of_true"),
            "blind_mean_rank_of_true": agg(blind_rows, "rank_of_true"),
            "trained_total_work": sum(r["total_work"] for r in trained_rows),
            "blind_total_work": sum(r["total_work"] for r in blind_rows),
        },
    }
