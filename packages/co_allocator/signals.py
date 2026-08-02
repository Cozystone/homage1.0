# -*- coding: utf-8 -*-
"""signals — adapters that turn ATANOR's REAL cognitive organs into the allocator's cheap feature
vector. Every adapter calls an existing, already-proved module read-only; nothing is fabricated.

The features (docs/ATANOR_final_gate_research.md §4, the escalate-score dot product):

  f0  1 - felt_conf(FOR)   low "feeling of rightness" about R0's answer  -> escalate
  f1  X1 compression-prog  VOC proxy: "will more computation change the answer?" -> escalate
  f2  conflict             competing R0 candidates of similar strength   -> escalate
  f3  abstain_margin       how close R0's best edge sits to the abstain floor -> escalate
  f4  difficulty_prior     a CHEAP query-shape estimate (composition / multi-entity) -> escalate
  f5  remaining_budget     normalized budget left (a scalar the loop supplies)

WIRING (real vs stand-in), stated honestly like the M1/M3 receipts:
  * felt_conf / conflict / abstain_margin  -> REAL. felt_judgment(...) ranks R0's candidate answers
    (merit = their spread activation); FOR = the winning margin, conflict = runner-up closeness.
    The felt STATE is neutral in the probe (no live hormones) for reproducibility — so FOR reduces to
    the activation-margin the body would then modulate. read_live_felt_state() is the live hook.
  * X1 (f1)  -> REAL. compression_progress.interestingness(answer_tree, known_blocks): if R0's answer
    edge is already a known block it is cheap to express (settled, low progress); a novel/ungrounded
    answer structure is dear (high progress). This is the module's own signal, used unmodified.
  * difficulty_prior (f4)  -> a CHEAP structural heuristic computed here (a control feature, not
    knowledge): counts entities / comparison-and-composition markers in the query text. Declared, not
    learned; the same category as the deliberator's COST_RANK. Listed as a stand-in for a learned prior.
  * conflict also has a REAL structural sibling in graph_scale.contradiction_gate (taxonomy DAG
    violations); it is NOT wired per-query here because it needs the columnar store (out of scope —
    S1 is writing data/graph_scale). The activation-margin conflict is what the loop consumes.
"""
from __future__ import annotations

from typing import Any, Callable

# REAL organs (imported, never edited) ------------------------------------------------------------
from packages.subjective.felt_judgment import felt_judgment, FeltState
from packages.evolution.compression_progress import interestingness
from packages.graph_scale.spreading_activation import _THRESHOLD

# An explicit NEUTRAL felt body for the probe: flat hormones, no vitals, no markers. Passing this
# (instead of None) stops felt_judgment from reading ATANOR's LIVE self_state.json / live somatic
# index — which would make the measurement non-reproducible (the live body tips concept scores). The
# live body is the intended production hook: pass a live FeltState as `context` to engage the full
# organ; the probe stays neutral so FOR reduces to the honest activation margin.
_NEUTRAL_FELT = FeltState()


# ── tree encoding (the grammar compression_progress consumes) ────────────────────────────────────

def edge_tree(subject: str, predicate: str, obj: str) -> tuple:
    """Encode a stored edge as a tuple-tree block: (ask (rel P) (of S) (val O)). This is the shape
    compression_progress anti-unifies over — a fixed 3-arg skeleton so two edges that differ only in
    their entities/relation share a >=2-node body (the 'learnable' factor fires) while a genuinely
    different structure does not."""
    return ("ask", ("rel", str(predicate)), ("of", str(subject)), ("val", str(obj)))


def known_blocks(facts_about: Callable[[str], list], anchor: str, *, radius_terms: tuple = ()) -> list:
    """The library the VOC proxy compresses against: the edge-trees ATANOR already holds around the
    query. We take the anchor's own edges plus those of any supplied neighbour terms — the concrete
    structure R0 can see. A candidate answer that IS one of these blocks is 'settled'."""
    blocks: list = []
    seen: set = set()
    for term in (anchor, *radius_terms):
        try:
            rows = facts_about(term) or []
        except Exception:
            rows = []
        for s, p, o in rows:
            t = edge_tree(s, p, o)
            if t not in seen:
                seen.add(t)
                blocks.append(t)
    return blocks


def x1_voc(answer_tree: tuple | None, blocks: list) -> float:
    """f1 — the X1 compression-progress VOC proxy, in [0, 1]. REAL: compression_progress.
    interestingness over the whitelisted tuple grammar. High = the answer is novel structure the
    library cannot yet cheaply express (more computation could still change/settle it); low = the
    answer is already a known, compressible block (settled — extra compute is unlikely to move it).

    An ungrounded R0 (answer_tree is None) returns the maximum VOC (1.0): there is nothing settled,
    so more computation is maximally worth spending — the honest 'I do not have this yet'."""
    if answer_tree is None:
        return 1.0
    if not blocks:
        return 1.0
    return float(interestingness(answer_tree, {"blocks": blocks}))


# ── felt confidence / conflict / abstain-margin (from the real felt organ) ───────────────────────

def _norm_options(candidates: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """Turn (answer_label, activation) pairs into felt_judgment option dicts with merit in [0,1]
    (activation normalized by the strongest). Grounded merit only — never fabricated."""
    if not candidates:
        return []
    top = max(a for _, a in candidates) or 1.0
    opts = []
    for label, act in candidates:
        # NB: no 'concepts' key — that would trigger a LIVE somatic-marker lookup and make the probe
        # non-reproducible. In production, attach concepts + a live FeltState to engage the somatic tips.
        opts.append({"id": str(label), "merit": max(0.0, min(1.0, act / top))})
    return opts


_RIVAL_FRACTION = 0.7             # a concept must reach 70% of the winner's activation to count as a
                                  # genuine rival ANSWER — below that it does not threaten the answer.


def felt_confidence(winner: str | None, winner_act: float, rivals: list[tuple[str, float]], *,
                    grounded: bool, context: Any = None) -> dict[str, float]:
    """FOR / conflict / abstain-margin for R0's answer, via the REAL felt_judgment organ.

    winner:     R0's proposed answer (object of the asked/intent edge, or a guessed neighbour).
    winner_act: its raw spread activation (for the abstain-floor distance).
    rivals:     (label, activation) for OTHER concepts that reach >= _RIVAL_FRACTION of the winner —
                i.e. concepts that genuinely threaten the answer (a competing answer or a distractor
                out-lighting it). A concept far below the winner is not a rival (no contest).
    grounded:   did R0 read a real intent edge (True) or only guess a neighbour (False)?

    The winner + its genuine rivals are ranked by felt_judgment (the real organ). Returns
    {for_conf, conflict, abstain_margin} in [0,1]:
      for_conf      = felt margin of the winner over its strongest rival (1.0 if uncontested) x gate
      conflict      = strongest-rival felt_score / winner felt_score (0 = uncontested, ->1 = tie)
      abstain_margin= how far below a comfort band the winner's activation sits (near the abstain floor)
    """
    if winner is None or winner_act <= 0:
        return {"for_conf": 0.0, "conflict": 1.0, "abstain_margin": 1.0}

    real_rivals = [(c, a) for c, a in rivals if c != winner and a >= _RIVAL_FRACTION * winner_act]
    opts = _norm_options([(winner, winner_act), *real_rivals])
    j = felt_judgment(opts, context if context is not None else _NEUTRAL_FELT)
    ranked = j.get("ranked", [])
    scores = sorted((r["felt_score"] for r in ranked), reverse=True)
    top = scores[0] if scores else 0.0
    second = scores[1] if len(scores) > 1 else 0.0

    margin = (top - second) if len(scores) > 1 else min(1.0, top)
    conflict = (second / top) if (top > 0 and len(scores) > 1) else 0.0
    for_conf = max(0.0, min(1.0, margin))
    if not grounded:
        for_conf *= 0.35          # a guessed neighbour is never fully "felt right"

    comfort = 3.0 * _THRESHOLD    # a band above the hard abstain floor where confidence is comfortable
    abstain_margin = 0.0 if winner_act >= comfort else max(0.0, min(1.0, (comfort - winner_act) / comfort))

    return {"for_conf": float(for_conf), "conflict": float(max(0.0, min(1.0, conflict))),
            "abstain_margin": float(abstain_margin)}


# ── difficulty prior (a cheap, declared query-shape feature) ─────────────────────────────────────

_COMPOSITION_MARKERS = (
    " and ", " then ", " within ", " more than ", " less than ", " enough", " exceed",
    " before ", " after ", " both ", " reach ", " in time", " compared", " than ",
    " does ", " will ", " if ",
)


def difficulty_prior(query_text: str) -> float:
    """f4 — a CHEAP structural difficulty estimate in [0, 1]. NOT knowledge and NOT learned: it counts
    surface markers of composition / multi-entity / comparison in the question shape. A single-fact
    'what is the capital of X' scores near 0; a 'can it reach Y in time AND stay under Z' scores high.

    Declared control feature (the research's 'difficulty prior'), listed as a stand-in for a learned
    difficulty model. Deliberately shape-only so it can never smuggle a domain fact."""
    q = f" {str(query_text or '').lower().strip()} "
    marks = sum(1 for m in _COMPOSITION_MARKERS if m in q)
    # capitalized-entity-ish tokens are a crude arity proxy; count distinct al3+ words after 'of'/'the'
    words = [w.strip(",.?!") for w in str(query_text or "").split()]
    long_words = len({w.lower() for w in words if len(w) >= 4})
    score = 0.18 * marks + 0.02 * long_words
    return float(max(0.0, min(1.0, score)))
