# -*- coding: utf-8 -*-
"""H4 — THE GENERATIVE PROPOSER (Switch 2 v1, the genuinely-new organ).

This is the piece `meta_diagnose.propose_novel_module` marks as the frontier (a NotImplementedError
stub) and the piece the whole H4 task is about: given a synthesis WALL, INVENT a new scheme to cross it
— not RETRIEVE a known one. It works from three inputs and NOTHING else (autonomy — no human-written
spec of the answer):

  1. the FAILURE SIGNATURE of the wall (trace_signature) — the structural gap,
  2. the RECIPE LEDGER (schemes that cracked structurally-resonant past walls),
  3. the AUXILIARY BASIS + the two structural MOVES (the composable meta-basis of schemes).

MECHANISM — GENERATIVE-VIA-COMPOSITION (the honest v1 floor)
-----------------------------------------------------------
The proposer RECOMBINES/MUTATES existing schemes+auxiliaries into candidate NEW schemes:

  * LIFT   — a meta-basis binary op (max2/min2/add/mul) becomes a running-aggregate auxiliary
             (scheme_space.lift). The base vocabulary; also how a COMPUTED-PROJECTION scheme's
             auxiliaries are formed (range = lift(max2)+lift(min2), output = a projection over them).
  * GROW   — append an auxiliary and put the OUTPUT on the new top component: a depth-k projection
             chain. The decisive move for order statistics — and the compounding channel, because the
             INVENTED output-step of depth k (relativised at promotion) is exactly the auxiliary the
             depth-(k+1) chain needs (scheme_space.relativize / instantiate_rel). So one genuine
             invention (the "next order statistic" step, discovered at k=2) lets EVERY deeper wall be
             crossed by ANALOGY — instantiate the promoted template at the new top index and VERIFY,
             with ZERO search. That is the self-acceleration the ledger unlocks.

RANKING — the candidates are ordered by the REUSED FHRR ALGEBRAIC RANKER
(`vsa_reasoning.behavior_signature.rank_candidates`): each candidate maps to a GENERIC prototype
recogniser (order statistic / aggregate, derived structurally from the config, task-INDEPENDENT — the
X4.5 "recognition vocabulary, not the answer" discipline), and prototypes are ranked by phasor resonance
to the target I/O. MDL breaks near-ties toward the shallower scheme (Occam). The ranker only ORDERS the
search; every returned scheme still passes the exact RE-EXECUTION anchor (propose-verify; 0 fabrication).

THE v2 FRONTIER (named, not faked). This v1 RECOMBINES a fixed move-set and ranks with hand-derived
prototypes. The one place a small LEARNED recogniser (N3-legal — sub-25M, propose-only) would turn
recombination into OPEN-ENDED generation is `_prototype_of` / the move-set: a recogniser trained on
(failure-signature -> winning-scheme) recipes would (a) PREDICT the winning scheme config directly from a
novel failure signature (no prototype library), and (b) propose move-compositions the fixed set cannot
express. It is deliberately NOT trained here — v1 measures exactly how far pure recombination + the
ledger get, so the learned recogniser's marginal value is measurable, not assumed.

Deterministic, No-LLM, numpy + stdlib.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from packages.self_acceleration import scheme_space as sp
from packages.self_acceleration import ledger as _ledger
from packages.vsa_reasoning.behavior_signature import rank_candidates

MAX_DEPTH = 7                       # bound the candidate accumulator arity (keeps the proposal set finite)


def _find_aux(basis: list[sp.Aux], name: str) -> sp.Aux | None:
    for a in basis:
        if a.name == name:
            return a
    return None


def _invented_order_template(basis: list[sp.Aux]) -> sp.Aux | None:
    """The promoted 'next order statistic' auxiliary, if H4 has invented it (provenance 'invented@...').
    This single template is what lets an order-stat chain grow to arbitrary depth (the compounding key)."""
    for a in basis:
        if a.provenance.startswith("invented"):
            return a
    return None


def _order_stat_chain(depth: int, basis: list[sp.Aux]) -> list[sp.Aux] | None:
    """Build the canonical order-statistic auxiliary chain for a depth-`depth` projection scheme:
    index 0 = running_max (generic LIFT), indices 1..depth-2 = the INVENTED order-stat template. Returns
    the (depth-1)-length chain, or None if the invented template is required (depth>=3) but absent (the
    frozen baseline's hard ceiling — it cannot build an order-stat aux beyond running_max)."""
    rmax = _find_aux(basis, "running_max")
    if rmax is None or depth < 2:
        return None
    chain = [rmax]
    if depth >= 3:
        T = _invented_order_template(basis)
        if T is None:
            return None
        chain += [T] * (depth - 2)              # the SAME template instantiated per-position at assembly
    return chain


# --- computed-projection recipe configs (the LIFT+PROJECT move) — a small, generic, task-independent set
_COMPUTED_RECIPES = (
    {"label": "range", "aux_names": ("running_max", "running_min"), "prototype": "range"},
    {"label": "amplitude_sum", "aux_names": ("running_sum",), "prototype": "sum"},
)


def _prototype_of(config: dict) -> Callable[[dict], Any]:
    """Map a candidate scheme config to its GENERIC prototype recogniser (the v2 learned-recogniser
    seam — see module docstring). Task-independent: the SAME prototype for every target."""
    if config["family"] == "projection_chain":
        return sp.order_stat_prototype(config["depth"])
    return sp.computed_prototype(config["prototype"])


def propose(failure_sig: np.ndarray, spec: list, basis: list[sp.Aux], ledger: "_ledger.SchemeLedger", *,
            use_ledger: bool = True, max_depth: int = MAX_DEPTH,
            retrieval_threshold: float = _ledger.DEFAULT_RETRIEVAL_THRESHOLD) -> dict:
    """Propose a RANKED list of candidate NEW schemes for a wall.

    Returns {"candidates": [config, ...] ranked best-first, "retrieval": <ledger match audit>}. Each
    config carries its resolved `aux_chain`, the `analogy_template` (a promoted step to reuse by index
    shift, when the ledger/basis provides one — the compounding shortcut), and its `prototype` for the
    ranker. GENERATION, not retrieval: the retrieved recipe SEEDS the grow move (which depth to extend
    to and which template to re-index); the proposer still EMITS a scheme never stored (a deeper chain),
    and the verifier gates it."""
    # (1) retrieval — a resonant past recipe RECOGNISES the failure family and hands back the promoted
    # step template. Gated on the ledger (use_ledger): promotion (basis growth) lets the proposer BUILD a
    # deeper chain, but only the ledger's family-recognition PERMITS reusing the invented output-step by
    # analogy. That split is exactly what separates the three ablations — see the module docstring.
    _empty = {"best": None, "best_similarity": 0.0, "matches": []}
    retrieval = ledger.retrieve(failure_sig, threshold=retrieval_threshold) if use_ledger else _empty
    # seed the GROW move from the best-resonant PROJECTION-CHAIN recipe (a computed-projection recipe
    # cannot seed a projection-chain analogy), family-filtered so a tie with a computed recipe never
    # steals the seed.
    seed = ledger.retrieve(failure_sig, threshold=retrieval_threshold,
                           family="projection_chain") if use_ledger else _empty
    seed_template = seed["best"]["scheme"].get("out_step_template") if seed["best"] is not None else None

    # (2) generate candidate configs by the GROW and LIFT+PROJECT moves
    configs: list[dict] = []
    for depth in range(2, max_depth + 1):
        chain = _order_stat_chain(depth, basis)
        if chain is None:
            continue                                                   # depth unreachable with this basis
        # the analogy shortcut for the OUTPUT step fires ONLY when the ledger recognised a resonant
        # projection-chain family (seed_template); without it the output step is OE-searched afresh.
        use_analogy = seed_template
        configs.append({
            "family": "projection_chain", "depth": depth, "aux_chain": chain,
            "aux_names": tuple(a.name for a in chain) + ("<output>",), "out_init": 0,
            "analogy_template": use_analogy, "move": "grow",
            "label": f"projection_chain(depth={depth})",
        })
    for rc in _COMPUTED_RECIPES:
        chain = [_find_aux(basis, n) for n in rc["aux_names"]]
        if any(a is None for a in chain):
            continue
        configs.append({
            "family": "computed_projection", "depth": len(chain), "aux_chain": chain,
            "aux_names": rc["aux_names"], "prototype": rc["prototype"], "analogy_template": None,
            "move": "lift+project", "label": f"computed_projection({rc['label']})",
        })

    # (3) rank by the REUSED FHRR algebraic ranker (prototype resonance to the target I/O), MDL tiebreak
    prototypes = {c["label"]: _prototype_of(c) for c in configs}
    ranked = rank_candidates(spec, prototypes) if configs else []
    score = {label: s for label, s in ranked}
    order = sorted(configs, key=lambda c: (-score.get(c["label"], -1.0), c["depth"]))   # resonance, then MDL
    for c in order:
        c["rank_score"] = round(float(score.get(c["label"], 0.0)), 4)
    return {"candidates": order, "retrieval": retrieval,
            "ranked_scores": [(c["label"], c["rank_score"]) for c in order[:5]]}
