# -*- coding: utf-8 -*-
"""H4 — THE SELF-ACCELERATION LOOP + the SIGNAL-4 harness (owner's "특히 4번").

THE LOOP (on the invention engine's OWN synthesis walls)
--------------------------------------------------------
For each target wall:
  1. WALL DETECTION — the CURRENT vocabulary (the X4.4 identity scalar fold) is proved insufficient by a
     FUNCTIONAL CONFLICT in its deduction (trace_signature; the honest X4.4/X4.5 state-insufficiency
     signal). Conflict => wall.
  2. FAILURE SIGNATURE — FHRR-encode the structural trace gap (trace_signature.signature).
  3. GENERATIVE PROPOSER — invent candidate NEW schemes by recombination (proposer.propose): grow an
     accumulator, lift a primitive, reuse a promoted step by analogy, ranked by the VSA algebraic ranker
     + MDL, seeded by the ledger's recognition of the failure family.
  4. SYNTHESISE + VERIFY — add each proposed scheme, re-attempt synthesis, keep ONLY a scheme that
     RE-EXECUTES correctly on held-out examples (the no-fabrication gate).
  5. PROMOTE + RECORD + COMPOUND — a verified projection-chain's invented output-step is relativised and
     promoted into the auxiliary basis (so a deeper wall can build on it), and the recipe (failure_sig ->
     scheme -> wall) is recorded in the ledger. Now available for future walls.

SIGNAL 4 — does improvement ACCELERATE? The harness runs the SAME curriculum under three ablations and
plots evals-per-wall:
  * H4                = invent + ledger  (full loop)
  * frozen_no_ledger  = invent, no ledger  (promotion grows the basis, but every output-step is
                        OE-searched afresh — isolates the ledger's analogy contribution)
  * frozen_no_invent  = no invention  (the accumulator basis never grows — the honest "no self-improvement"
                        control; cannot build an order-stat aux beyond running_max)
and reports, SEALED and HONEST, the walls-crossed counts and whether H4's per-wall search cost
ACCELERATES (decreasing), is LINEAR (flat), or DECELERATES/PLATEAUS.

Deterministic, No-LLM, numpy + stdlib.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from packages.evolution import open_domain as od
from packages.evolution import scheme_synthesis as ss
from packages.self_acceleration import scheme_space as sp
from packages.self_acceleration import trace_signature as tsig
from packages.self_acceleration import proposer as _proposer
from packages.self_acceleration.ledger import SchemeLedger
from packages.self_acceleration.curriculum import CURRICULUM, Wall


# ============================================================================================
# STATE — the growing vocabulary + the recipe flywheel.
# ============================================================================================
def fresh_state() -> dict[str, Any]:
    return {"basis": sp.base_aux_basis(), "ledger": SchemeLedger(), "invented_sources": set()}


def _to_json(t: Any) -> Any:
    """Tuple tree -> nested lists for JSON storage in the ledger (thawed back on retrieval)."""
    if isinstance(t, tuple):
        return [_to_json(x) for x in t]
    return t


def _promote(state: dict, template: Any, wall_name: str) -> bool:
    """Promote a verified output-step template into the auxiliary basis as a reusable order-stat aux
    (dedup by source). This is the compounding channel: the invented step of one wall becomes an
    auxiliary the next wall's chain is built from."""
    src = od.to_source(template)
    if src in state["invented_sources"]:
        return False
    state["invented_sources"].add(src)
    state["basis"].append(sp.Aux(name=f"order_stat({src})", template=template, init=-sp.CLAMP,
                                 provenance=f"invented@{wall_name}"))
    return True


# ============================================================================================
# RESULT
# ============================================================================================
@dataclass
class WallResult:
    name: str
    crossed: bool
    is_wall: bool = True                 # False if the base vocabulary already solved it (not a wall)
    via: str = ""                        # "analogy" | "oe" | "computed-proj" | ""
    scheme: str = ""
    depth: int = 0
    synth_evals: int = 0                 # OE candidate evaluations (the search cost)
    verify_execs: int = 0                # whole-program re-executions (the propose-verify cost)
    proposals_tried: int = 0
    invented_new_template: bool = False
    reused_analogy: bool = False
    retrieval_similarity: float = 0.0
    program: str = ""

    @property
    def total_work(self) -> int:
        return self.synth_evals + self.verify_execs


# ============================================================================================
# CROSS ONE WALL
# ============================================================================================
def cross_wall(wall: Wall, state: dict, rng: random.Random, *, invent: bool = True,
               use_ledger: bool = True, max_fallback: int = 5,
               n_outer: int = 10, n_verify: int = 14, n_holdout: int = 40) -> WallResult:
    listvar = wall.listvar
    spec = wall.samples(16, rng)
    outer = wall.outer(n_outer, rng)
    verify = wall.samples(n_verify, rng)
    holdout = wall.samples(n_holdout, rng)

    # (1) wall detection — the scalar-fold FUNCTIONAL CONFLICT (computed on the PREFIX-CLOSED oracle I/O)
    # is the honest proof the current base vocabulary (identity scalar fold) cannot express the target
    # (X4.4/X4.5 state-insufficiency). A synthesis system legitimately queries the oracle on prefixes.
    conflict = tsig.conflict_from_outer(outer, listvar)
    features = tsig.trace_features(spec, conflict=conflict)
    if not features["scalar_fold_conflict"]:
        # no conflict: confirm with a bounded base identity-fold attempt before declaring not-a-wall
        base = ss.synthesize_fold(outer, listvar, verify, step_binary=("cat", "add", "mul", "min2", "max2"),
                                  step_filter=True, step_pred_vars=("_x", "_e"), step_pred_consts=(0, 1),
                                  max_nodes=14, time_budget=8.0)
        if base.get("solved") and od.fitness(base["tree"], holdout) >= 1.0:
            return WallResult(wall.name, crossed=True, is_wall=False, via="base-identity-fold",
                              scheme="identity_scalar_fold", program=base.get("program", ""))

    # (2) failure signature over the synthesis trace
    sig = tsig.encode_features(features)

    # (3) generative proposer
    prop = _proposer.propose(sig, spec, state["basis"], state["ledger"], use_ledger=use_ledger)
    retrieval_sim = prop["retrieval"]["best_similarity"]

    # (4) synthesise + verify, ranked order, propose-verify gated
    synth_evals = verify_execs = tried = 0
    for c in prop["candidates"][:max_fallback]:
        tried += 1
        if c["family"] == "projection_chain":
            r = sp.synthesize_projection_chain(outer, listvar, verify, c["aux_chain"],
                                               out_init=c["out_init"],
                                               analogy_template=c["analogy_template"])
        else:
            r = sp.synthesize_computed_projection(outer, listvar, verify, c["aux_chain"])
        synth_evals += r["synth_evals"]
        verify_execs += r["verify_execs"]
        if not r.get("solved"):
            continue
        # generalisation gate: re-execute on a larger unseen holdout (propose-verify, no fabrication)
        ho_fit = od.fitness(r["tree"], holdout)
        verify_execs += len(holdout)
        if ho_fit < 1.0:
            continue
        # (5) promote + record + compound
        invented_new = False
        if invent:
            if c["family"] == "projection_chain" and r.get("out_step_template") is not None:
                invented_new = _promote(state, r["out_step_template"], wall.name)
                scheme_rec = {"family": "projection_chain", "depth": r["k"],
                              "out_step_template": _to_json(r["out_step_template"])}
            else:
                scheme_rec = {"family": c["family"], "depth": r.get("k", c["depth"]),
                              "out_step_template": None}
            state["ledger"].add(sig, scheme_rec, wall.name)
        return WallResult(wall.name, crossed=True, via=r["via"], scheme=c["label"], depth=r.get("k", 0),
                          synth_evals=synth_evals, verify_execs=verify_execs, proposals_tried=tried,
                          invented_new_template=invented_new, reused_analogy=(r["via"] == "analogy"),
                          retrieval_similarity=retrieval_sim, program=r.get("program", ""))

    return WallResult(wall.name, crossed=False, via="", scheme="", synth_evals=synth_evals,
                      verify_execs=verify_execs, proposals_tried=tried, retrieval_similarity=retrieval_sim)


# ============================================================================================
# RUN THE CURRICULUM under one ablation
# ============================================================================================
def run_curriculum(walls: list[Wall] | None = None, *, invent: bool = True, use_ledger: bool = True,
                   seed: int = 7) -> dict[str, Any]:
    walls = walls or CURRICULUM
    state = fresh_state()
    rng = random.Random(seed)
    results: list[WallResult] = []
    for w in walls:
        results.append(cross_wall(w, state, rng, invent=invent, use_ledger=use_ledger))
    crossed = [r for r in results if r.crossed and r.is_wall]
    return {
        "config": {"invent": invent, "use_ledger": use_ledger, "seed": seed},
        "results": results,
        "walls_crossed": len(crossed),
        "walls_total": len([w for w in walls]),
        "final_basis_size": len(state["basis"]),
        "invented_templates": len(state["invented_sources"]),
        "ledger_size": len(state["ledger"]),
    }


# ============================================================================================
# SIGNAL 4 — the sealed measurement
# ============================================================================================
_SPINE = ("second_max", "third_max", "fourth_max", "fifth_max")   # the compounding order-statistic ladder


def _spine_curve(results: list[WallResult], key: str = "synth_evals") -> list:
    by = {r.name: r for r in results}
    return [(getattr(by[n], key) if (n in by and by[n].crossed) else None) for n in _SPINE]


def _second_difference(xs: list) -> float | None:
    """Discrete a2: mean second difference of a numeric sequence (sign = curvature). Negative =>
    decelerating growth / accelerating drop; used on the spine synth-eval curve."""
    v = [x for x in xs if isinstance(x, (int, float))]
    if len(v) < 3:
        return None
    sd = [v[i + 2] - 2 * v[i + 1] + v[i] for i in range(len(v) - 2)]
    return sum(sd) / len(sd)


def signal4(seed: int = 7) -> dict[str, Any]:
    """Run the curriculum under the three ablations and compute the honest signal-4 verdict."""
    h4 = run_curriculum(invent=True, use_ledger=True, seed=seed)
    frozen_no_ledger = run_curriculum(invent=True, use_ledger=False, seed=seed)
    frozen_no_invent = run_curriculum(invent=False, use_ledger=False, seed=seed)

    h4_spine = _spine_curve(h4["results"])
    fnl_spine = _spine_curve(frozen_no_ledger["results"])
    fni_spine = _spine_curve(frozen_no_invent["results"])

    # per-wall TOTAL work (synth + verify) for the full curriculum, in order
    def total_curve(run):
        return [(r.name, r.total_work if r.crossed else None, r.crossed, r.via) for r in run["results"]]

    # compounding measures
    h4_spine_vals = [x for x in h4_spine if x is not None]
    first = h4_spine_vals[0] if h4_spine_vals else None
    later = h4_spine_vals[1:] if len(h4_spine_vals) > 1 else []
    mean_later = (sum(later) / len(later)) if later else None
    accel_ratio = (first / mean_later) if (first and mean_later not in (None, 0)) else (
        float("inf") if (first and mean_later == 0) else None)

    if len(h4_spine_vals) >= 2:
        if mean_later is not None and first is not None and mean_later < 0.5 * first:
            rate_verdict = "ACCELERATING (per-wall search cost drops sharply after the first invention)"
        elif mean_later is not None and first is not None and mean_later <= 1.15 * first:
            rate_verdict = "LINEAR (per-wall search cost roughly flat)"
        else:
            rate_verdict = "DECELERATING (per-wall search cost grows)"
    else:
        rate_verdict = "INSUFFICIENT DATA (fewer than 2 spine walls crossed)"

    return {
        "seed": seed,
        "walls_crossed": {"H4": h4["walls_crossed"], "frozen_no_ledger": frozen_no_ledger["walls_crossed"],
                          "frozen_no_invent": frozen_no_invent["walls_crossed"],
                          "total": h4["walls_total"]},
        "spine_synth_evals": {"H4": h4_spine, "frozen_no_ledger": fnl_spine, "frozen_no_invent": fni_spine,
                              "order": list(_SPINE)},
        "spine_a2": {"H4": _second_difference(h4_spine), "frozen_no_ledger": _second_difference(fnl_spine)},
        "total_work_curve": {"H4": total_curve(h4), "frozen_no_ledger": total_curve(frozen_no_ledger),
                             "frozen_no_invent": total_curve(frozen_no_invent)},
        "accel_ratio_first_over_later": accel_ratio,
        "rate_verdict": rate_verdict,
        "runs": {"H4": h4, "frozen_no_ledger": frozen_no_ledger, "frozen_no_invent": frozen_no_invent},
    }
