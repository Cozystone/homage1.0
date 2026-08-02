# -*- coding: utf-8 -*-
"""H4 v2 — the CROSS-FAMILY self-acceleration loop + the honest signal-4 harness.

THE LOOP (v2)
-------------
Same skeleton as v1's `h4.cross_wall`, with ONE organ swapped: the ranker. Where v1 ranks candidate
schemes with hand-derived prototypes over a fixed move-set (`proposer._prototype_of` + `_COMPUTED_RECIPES`),
v2 ranks the FULL move-composition space with the LEARNED `MoveRecognizer` (trained on the accumulating
recipe ledger). Everything else is v1, REUSED unchanged:
  * scheme_space.synthesize_projection_chain / synthesize_computed_projection  (the synthesisers)
  * the projection-chain PROMOTION + ledger analogy (the within-family compounding shortcut)
  * the RE-EXECUTION gate `od.fitness(prog, holdout) >= 1.0`  (propose-verify, zero fabrication)

The recogniser only ORDERS the candidate list; the loop still tries candidates in that order and accepts
ONLY one that re-executes on held-out examples. A mis-ranked proposal costs a failed search, never a
fabricated cross.

SIGNAL 4, CROSS-FAMILY (the honest deliverable)
-----------------------------------------------
`signal4_cross_family` runs the four-family curriculum under three ablations and reports per-wall work:
  * v2_recognizer       — learned recogniser, retrained on the accumulating ledger before each wall.
  * frozen_no_recognizer— same net, NEVER trained (random-init forward pass = blind Occam order). The
                          "no learning" control.
  * v1_proposer         — v1's ACTUAL `h4.cross_wall` (fixed move-set + hand prototypes), run on the same
                          walls (duck-typed CFWall). Documents v1's move-set CEILING: it cannot express
                          the summin/summax families at all.
`heldout_family_transfer` trains the recogniser on THREE families, FREEZES it, and faces the FOURTH cold
— the acid test that separates "learned the structure (transfers)" from "memorised these families".

No-LLM, numpy + stdlib, deterministic.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from packages.evolution import open_domain as od
from packages.evolution import scheme_synthesis as ss
from packages.self_acceleration import scheme_space as sp
from packages.self_acceleration import trace_signature as tsig
from packages.self_acceleration import structural_features as sf
from packages.self_acceleration import proposer as _v1_proposer
from packages.self_acceleration import h4 as _h4
from packages.self_acceleration.ledger import SchemeLedger
from packages.self_acceleration.recognizer import (
    MoveRecognizer, MoveComposition, RecipeExample, all_compositions, AUX_OPS, FAMILIES as _FAMS,
)
from packages.self_acceleration import cross_family_curriculum as cur
from packages.vsa_reasoning.behavior_signature import rank_candidates

# OE budgets for the measurement — bounded so a mis-ranked (failed) search is cheap and the whole
# harness runs in a couple of minutes. synth_evals (deterministic) is the primary cost metric.
_PROJ_NODE_BUDGET = 20000
_PROJ_TIME_BUDGET = 4.0
_COMP_NODE_BUDGET = 8000
_COMP_TIME_BUDGET = 2.0


def fresh_state() -> dict[str, Any]:
    """The growing vocabulary + the recipe flywheel. `recipes` is the recogniser's training set
    (feature_vector -> winning composition); `ledger` is v1's SchemeLedger (projection analogy)."""
    return {"basis": sp.base_aux_basis(), "ledger": SchemeLedger(), "invented_sources": set(),
            "recipes": []}


# ============================================================================================
# COMPOSITION EXPANSION — a MoveComposition -> a scheme_space synthesis attempt (v1 machinery, reused).
# ============================================================================================
def _seed_analogy_template(state: dict, fhrr_sig, use_ledger: bool):
    if not use_ledger:
        return None
    seed = state["ledger"].retrieve(fhrr_sig, family="projection_chain")
    if seed["best"] is None:
        return None
    return seed["best"]["scheme"].get("out_step_template")


def _expand_and_synthesize(comp: MoveComposition, wall, outer, verify, state: dict, fhrr_sig,
                           use_ledger: bool) -> dict:
    """Run the scheme_space synthesiser for one candidate composition. Returns the v1 result dict
    (solved, via, synth_evals, verify_execs, out_step_template, tree, ...). A composition unbuildable
    with the current basis (projection depth>=3 without the promoted template) returns solved=False at
    zero cost (honest reachability degradation)."""
    listvar = wall.listvar
    if comp.family == "projection_chain":
        chain = _v1_proposer._order_stat_chain(comp.depth, state["basis"])
        if chain is None:
            return {"solved": False, "via": "unreachable", "synth_evals": 0, "verify_execs": 0,
                    "k": comp.depth}
        analogy = _seed_analogy_template(state, fhrr_sig, use_ledger)
        return sp.synthesize_projection_chain(outer, listvar, verify, chain, out_init=0,
                                              analogy_template=analogy, node_budget=_PROJ_NODE_BUDGET,
                                              time_budget=_PROJ_TIME_BUDGET)
    # computed_projection
    chain = [sp.lift(op) for op in comp.aux_ops]
    return sp.synthesize_computed_projection(outer, listvar, verify, chain,
                                             node_budget=_COMP_NODE_BUDGET, time_budget=_COMP_TIME_BUDGET)


# ============================================================================================
# RESULT
# ============================================================================================
@dataclass
class WallResultV2:
    name: str
    family: str
    crossed: bool
    via: str = ""
    composition: str = ""
    synth_evals: int = 0
    verify_execs: int = 0
    candidates_tried: int = 0          # how many compositions were attempted (incl. failed) before success
    rank_of_winner: int = -1           # position of the winning composition in the recogniser's ranking
    reused_analogy: bool = False
    program: str = ""

    @property
    def total_work(self) -> int:
        return self.synth_evals + self.verify_execs


# ============================================================================================
# HYBRID RANKING — the LEARNED recogniser owns the CROSS-family decision (family-type + computed
# aux-set); projection-chain DEPTH ordering reuses v1's within-family resonance ranker (order_stat
# prototype), IDENTICALLY in every arm, so it is not the learned differential. This isolates the learned
# contribution to exactly the computed aux-set — the quantity the cross-family transfer test measures.
# ============================================================================================
def _proj_resonance(spec: list) -> dict[str, float]:
    """v1's within-family depth ranker (reused, NOT learned): resonance of each order-stat prototype to
    the target I/O. Maps projection_chain(depth=k).label -> resonance in [0,1]."""
    proj = [c for c in all_compositions() if c.family == "projection_chain"]
    protos = {c.label: sp.order_stat_prototype(c.depth) for c in proj}
    return {label: max(0.0, float(s)) for label, s in rank_candidates(spec, protos)}


def rank_for_wall(recognizer: MoveRecognizer, feats, spec: list) -> list[tuple[MoveComposition, float]]:
    """Rank the full composition space for a wall. Family gate + computed aux-set = LEARNED
    (recogniser); projection depth = v1 resonance (reused). Deterministic tie-break by Occam order."""
    pf, pa = recognizer.predict(feats)
    g_proj = float(pf[_FAMS.index("projection_chain")])
    comps = all_compositions()
    res = _proj_resonance(spec)
    order_index = {c.label: i for i, c in enumerate(comps)}
    scored = []
    for c in comps:
        if c.family == "projection_chain":
            s = g_proj * res.get(c.label, 0.0)
        else:
            s = recognizer.score_composition(pf, pa, c)      # g_comp * aux-set likelihood (learned)
        scored.append((c, s))
    scored.sort(key=lambda t: (-t[1], order_index[t[0].label]))
    return scored


# ============================================================================================
# CROSS ONE WALL (v2) — recogniser ranks; v1 machinery synthesises + verifies.
# ============================================================================================
def cross_wall_v2(wall, state: dict, recognizer: MoveRecognizer, rng: random.Random, *,
                  invent: bool = True, use_ledger: bool = True, record: bool = True,
                  n_outer: int = 10, n_verify: int = 14, n_holdout: int = 40) -> WallResultV2:
    listvar = wall.listvar
    spec = wall.samples(16, rng)
    outer = wall.outer(n_outer, rng)
    verify = wall.samples(n_verify, rng)
    holdout = wall.samples(n_holdout, rng)

    conflict = tsig.conflict_from_outer(outer, listvar)
    probe_rng = random.Random(hash((wall.name, "probe")) & 0xFFFFFFFF)
    feats = sf.feature_vector(spec, wall.oracle, probe_rng, conflict=conflict, listvar=listvar,
                              lo=wall.lo, hi=wall.hi, max_len=wall.max_len)
    fhrr_sig = sf.fhrr_signature(spec, conflict=conflict)

    ranked = rank_for_wall(recognizer, feats, spec)

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
        # --- verified cross: promote (projection) + record the recipe (the flywheel) ---
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
# RUN THE CURRICULUM under one recogniser mode
# ============================================================================================
def run_cross_family(mode: str, *, walls=None, seed: int = 7, hidden: int = 24,
                     epochs: int = 400) -> dict[str, Any]:
    """Run the four-family curriculum. mode in {"v2", "frozen"}:
      * "v2"     — retrain the recogniser on the accumulating recipe ledger BEFORE each wall (flywheel).
      * "frozen" — never train (random-init net = the no-learning / blind-Occam control).
    """
    walls = walls if walls is not None else cur.all_walls()
    state = fresh_state()
    rng = random.Random(seed)
    recognizer = MoveRecognizer(n_features=sf.N_FEATURES, hidden=hidden, seed=seed)
    results: list[WallResultV2] = []
    train_log: list[dict] = []
    for w in walls:
        if mode == "v2" and state["recipes"]:
            info = recognizer.fit(state["recipes"], epochs=epochs)
            train_log.append({"before_wall": w.name, "n_recipes": info["n"]})
        results.append(cross_wall_v2(w, state, recognizer, rng))
    crossed = [r for r in results if r.crossed]
    return {"mode": mode, "seed": seed, "results": results, "walls_crossed": len(crossed),
            "walls_total": len(walls), "final_basis_size": len(state["basis"]),
            "invented_templates": len(state["invented_sources"]), "ledger_size": len(state["ledger"]),
            "n_params": recognizer.n_params(), "recognizer": recognizer, "state": state,
            "train_log": train_log}


def run_v1_proposer(walls=None, *, seed: int = 7) -> dict[str, Any]:
    """The v1 hand-prototype baseline: v1's ACTUAL cross_wall on the same walls (duck-typed). v1's
    proposer only knows {range, sum} computed recipes + the order grow, so it crosses order + extent but
    CANNOT express summin/summax — the honest move-set ceiling."""
    walls = walls if walls is not None else cur.all_walls()
    state = _h4.fresh_state()
    rng = random.Random(seed)
    results = []
    for w in walls:
        r = _h4.cross_wall(w, state, rng, invent=True, use_ledger=True)
        results.append({"name": w.name, "family": getattr(w, "family", "?"), "crossed": bool(r.crossed),
                        "via": r.via, "total_work": r.total_work if r.crossed else None,
                        "synth_evals": r.synth_evals, "scheme": r.scheme})
    return {"mode": "v1_proposer", "results": results,
            "walls_crossed": sum(1 for r in results if r["crossed"]), "walls_total": len(walls)}


# ============================================================================================
# SIGNAL 4 — the sealed cross-family measurement
# ============================================================================================
def _work_curve(run: dict) -> list:
    return [(r.name, r.family, r.total_work if r.crossed else None, r.crossed, r.via,
             r.rank_of_winner, r.candidates_tried) for r in run["results"]]


def _first_wall_work(run: dict) -> dict[str, Any]:
    """Per-family FIRST-wall total_work (the cross-family transfer signal: does a NOVEL family's first
    wall get cheaper as the ledger grows)."""
    out: dict[str, Any] = {}
    for r in run["results"]:
        if r.family not in out:
            out[r.family] = r.total_work if r.crossed else None
    return out


def signal4_cross_family(seed: int = 7) -> dict[str, Any]:
    v2 = run_cross_family("v2", seed=seed)
    frozen = run_cross_family("frozen", seed=seed)
    v1 = run_v1_proposer(seed=seed)

    return {
        "seed": seed,
        "n_params": v2["n_params"],
        "walls_crossed": {"v2_recognizer": v2["walls_crossed"], "frozen_no_recognizer": frozen["walls_crossed"],
                          "v1_proposer": v1["walls_crossed"], "total": v2["walls_total"]},
        "work_curve": {"v2_recognizer": _work_curve(v2), "frozen_no_recognizer": _work_curve(frozen)},
        "v1_proposer_curve": [(r["name"], r["family"], r["total_work"], r["crossed"], r["via"])
                              for r in v1["results"]],
        "first_wall_work": {"v2_recognizer": _first_wall_work(v2),
                            "frozen_no_recognizer": _first_wall_work(frozen)},
        "runs": {"v2_recognizer": v2, "frozen_no_recognizer": frozen, "v1_proposer": v1},
    }


# ============================================================================================
# HELD-OUT FAMILY TRANSFER — the acid test (structure vs memorisation)
# ============================================================================================
def _true_composition(wall) -> MoveComposition:
    if wall.true_family == "projection_chain":
        return MoveComposition("projection_chain", depth=2)
    return MoveComposition("computed_projection", aux_ops=tuple(wall.true_aux))


def _rank_of_true_auxset(recognizer: MoveRecognizer, feats, spec, wall) -> dict[str, Any]:
    """Where does the recogniser place the TRUE aux-set (family + op-set) in its ranking? (Scoring only —
    the true aux-set is never shown to the recogniser; this just reads out its prediction quality.)"""
    ranked = rank_for_wall(recognizer, feats, spec)
    want_aux = frozenset(wall.true_aux)
    want_fam = wall.true_family
    for pos, (comp, score) in enumerate(ranked):
        same_fam = (comp.family == want_fam)
        same_aux = (frozenset(comp.aux_ops) == want_aux) if comp.family == "computed_projection" else True
        if same_fam and same_aux:
            return {"rank_of_true": pos, "score": round(float(score), 6), "top": ranked[0][0].label}
    return {"rank_of_true": -1, "score": 0.0, "top": ranked[0][0].label}


def heldout_family_transfer(holdout: str, *, seed: int = 7, epochs: int = 600) -> dict[str, Any]:
    """Train the recogniser on the recipes of every family EXCEPT `holdout`, freeze it, then face the
    held-out family's walls cold. Compare against the untrained (frozen-init) recogniser on the same
    walls. Transfer = the trained-on-others recogniser ranks the held-out family's TRUE composition
    higher / crosses its walls cheaper than blind."""
    train_families = [f for f in cur.FAMILY_ORDER if f != holdout]
    train_walls = [w for f in train_families for w in cur.walls_of(f)]
    holdout_walls = cur.walls_of(holdout)

    # (1) build the training ledger by running v2 over the training families
    state = fresh_state()
    rng = random.Random(seed)
    trained = MoveRecognizer(n_features=sf.N_FEATURES, seed=seed)
    for w in train_walls:
        if state["recipes"]:
            trained.fit(state["recipes"], epochs=epochs)
        cross_wall_v2(w, state, trained, rng)
    trained.fit(state["recipes"], epochs=epochs)   # final fit on ALL training-family recipes

    untrained = MoveRecognizer(n_features=sf.N_FEATURES, seed=seed)   # the blind control (never trained)

    # (2) face the held-out family cold with BOTH recognisers (fresh states; no recording, no ledger
    #     from the held-out family — a true cold-start on structurally-novel walls)
    def face(recog):
        st = fresh_state()
        r2 = random.Random(seed + 1)
        rows = []
        for w in holdout_walls:
            spec = w.samples(16, r2)
            outer = w.outer(10, r2)
            conflict = tsig.conflict_from_outer(outer, w.listvar)
            prng = random.Random(hash((w.name, "probe")) & 0xFFFFFFFF)
            feats = sf.feature_vector(spec, w.oracle, prng, conflict=conflict, listvar=w.listvar,
                                      lo=w.lo, hi=w.hi, max_len=w.max_len)
            pred = _rank_of_true_auxset(recog, feats, spec, w)
            res = cross_wall_v2(w, st, recog, r2, invent=True, use_ledger=True, record=False)
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
