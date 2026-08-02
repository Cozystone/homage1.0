# -*- coding: utf-8 -*-
"""Within-percept recurrent refinement — the deep sensory-cortex feedback loop RPT asks for.

Recurrent Processing Theory (RPT) associates consciousness with INPUT modules that use algorithmic
recurrence: a percept is not settled in one feed-forward pass but is refined by recurrent feedback
loops that fold TOP-DOWN context (prior / expectation) back onto the BOTTOM-UP sensory evidence until
the interpretation stabilises. ATANOR already had recurrence at the GATE level (attention.AttentionState
conditions processing on its own history) and at the SEQUENCE level (situation_model integrates a
sentence stream into a persistent WorldState). What was thin — and what this organ adds — is recurrence
WITHIN a single percept: taking one noisy/ambiguous read and iteratively sharpening it.

The mechanism (pure numpy, No-LLM, deterministic — a fixed-point iteration, not a trained net):

    b_0     = softmax(L)                                        # feed-forward read (the detector's soft scores)
    b_{t+1} = softmax( L + KAPPA * ( W_CTX*g + W_FB*log(b_t) ) )  # recurrent refinement step

  * L      — FIXED bottom-up evidence logits (the sensor's read of THIS object; never overwritten, so
             strong evidence always anchors the fixed point and cannot be talked out of a clear read).
  * g      — FIXED top-down context logits (scene expectation / plausibility prior; the prediction the
             rest of the system imposes on the percept). See `plausibility_prior`.
  * log(b_t) — the RECURRENT term: the current interpretation re-enters its own next update. This is
             what makes the module recurrent WITHIN the percept — the SAME evidence L is processed
             differently at each step depending on the accumulated belief state (the RPT signature),
             and different top-down context g settles the SAME evidence into a different percept.

Honesty is structural, not bolted on:
  * Convergence is GUARANTEED because the self-feedback gain KAPPA*W_FB = 0.27 < 1 makes the update a
    contraction (a unique fixed point it provably settles to). That same sub-critical gain is the
    ANTI-WIREHEADING guard: with flat evidence AND flat context the unique fixed point is EXACTLY the
    uniform distribution — the loop CANNOT manufacture confidence out of nothing. A percept only
    sharpens when the evidence or the context actually leans somewhere.
  * A percept is reported RESOLVED only if it converges to a confidence >= ACCEPT. If it converges but
    stays ambiguous (tied evidence, unhelpful context), or runs out of the iteration budget while still
    moving, the honest verdict is UNRESOLVED — we return the true low confidence and say so, never a
    rounded-up certainty. This is the "converges on some inputs, honestly gives up on others" boundary.

Zero learned parameters: KAPPA/W_CTX/W_FB/ACCEPT are curated dynamical set-points (the same category as
homeostasis set-points), not weights fit to data. Registered in the neuro ledger at 0 params.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

# ── curated dynamical set-points (NOT learned weights) ───────────────────────────────────────────
KAPPA = 0.9            # top-down feedback gain (how hard context+self-feedback pull on the evidence)
W_CTX = 0.70           # weight on the EXTERNAL top-down context prior
W_FB = 0.30            # weight on the RECURRENT self-consistency feedback (belief fed back into itself)
# invariant: KAPPA*W_FB (= 0.27) < 1  -> the update is a contraction: convergence is guaranteed AND flat
# input has a unique uniform fixed point (no confidence is fabricated). Assert it at import.
assert KAPPA * W_FB < 1.0, "self-feedback gain must stay sub-critical (guarantees convergence + honesty)"

MAX_ITER = 16          # iteration budget; running out is an honest 'did_not_stabilize' give-up
EPS = 1e-3             # convergence tolerance on the max change in the belief between steps
ACCEPT = 0.55          # a percept is RESOLVED only if it settles at >= this confidence
SHARPEN_MARGIN = 0.05  # "sharpened" means the settled confidence beat the feed-forward read by this much
_FLOOR = 1e-6          # clamp for scores before the log (avoid -inf)
_TINY = 1e-9

# a strongly-suppressing top-down logit for a candidate context deems (near-)impossible. Not -inf: the
# percept can still be rescued by overwhelming bottom-up evidence — top-down biases, it does not veto.
_IMPLAUSIBLE_LOGIT = float(np.log(0.02))


# ── result contract ──────────────────────────────────────────────────────────────────────────────
@dataclass
class RefinementTrace:
    """Everything measured about one recurrent refinement — enough to audit it, never a bare flag."""
    labels: list[str]
    initial: list[float]           # b_0: the feed-forward read (normalised detector scores)
    final: list[float]             # b_*: the settled percept
    trajectory: list[float]        # max-confidence at each iteration (the sharpening curve)
    winner: str                    # argmax of the settled percept
    winner_initial: str            # argmax of the feed-forward read (may differ: context flipped it)
    confidence: float              # max(final)
    initial_confidence: float      # max(initial)
    delta_confidence: float        # confidence - initial_confidence (how much it sharpened)
    iterations: int
    converged: bool                # stabilised (max belief change < EPS) within the budget
    resolved: bool                 # converged AND confidence >= ACCEPT (an honest, usable percept)
    flipped: bool                  # winner != winner_initial (top-down feedback overrode the read)
    status: str                    # sharpened | confirmed | unresolved_ambiguous | did_not_stabilize
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "labels": self.labels, "winner": self.winner, "winner_initial": self.winner_initial,
            "confidence": round(self.confidence, 4), "initial_confidence": round(self.initial_confidence, 4),
            "delta_confidence": round(self.delta_confidence, 4), "iterations": self.iterations,
            "converged": self.converged, "resolved": self.resolved, "flipped": self.flipped,
            "status": self.status, "trajectory": [round(x, 4) for x in self.trajectory], "notes": self.notes,
        }


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────
def _softmax(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def _as_logits(scores: Sequence[float]) -> np.ndarray:
    """Turn raw non-negative scores into a normalised log-distribution: softmax(_as_logits(s)) == s/sum(s)."""
    p = np.asarray(scores, dtype=np.float64)
    p = np.clip(p, _FLOOR, None)
    p = p / p.sum()
    return np.log(p)


# ── top-down context priors (wire real ATANOR perception organs) ─────────────────────────────────
def plausibility_prior(labels: Sequence[str]) -> np.ndarray:
    """A top-down context distribution from the perception plausibility organ: candidates that cannot
    physically be in an ordinary room (a whale, an airplane) are strongly down-weighted. This is the
    real ATANOR organ (packages/perception/plausibility.py) supplying the top-down prediction the
    recurrent loop folds onto the bottom-up read — so a detector's confident-but-impossible glimpse can
    be corrected by context instead of narrated as real."""
    from packages.perception import plausibility as pl

    logits = np.array([0.0 if pl.is_plausible_indoors(str(lb)) else _IMPLAUSIBLE_LOGIT
                       for lb in labels], dtype=np.float64)
    return _softmax(logits)


# ── the recurrent refinement loop ────────────────────────────────────────────────────────────────
def refine(labels: Sequence[str], scores: Sequence[float],
           context: Sequence[float] | None = None, *,
           kappa: float = KAPPA, w_ctx: float = W_CTX, w_fb: float = W_FB,
           max_iter: int = MAX_ITER, eps: float = EPS, accept: float = ACCEPT,
           sharpen_margin: float = SHARPEN_MARGIN) -> RefinementTrace:
    """Iteratively refine one noisy percept until it STABILISES or honestly gives up.

    labels/scores  — the candidate readings and their bottom-up evidence (a detector's soft scores for
                     ONE object). A low max-score is an ambiguous percept — the case RPT refinement is for.
    context        — an optional top-down prior over the SAME labels (e.g. `plausibility_prior(labels)`
                     or a scene expectation). None => uniform (the loop then leans only on the evidence's
                     own tilt via the bounded self-feedback, and cannot invent a tilt that is not there).

    Returns a RefinementTrace with the full confidence trajectory and an HONEST verdict.
    """
    labels = [str(x) for x in labels]
    if len(labels) < 1:
        raise ValueError("refine needs at least one candidate label")
    if len(scores) != len(labels):
        raise ValueError("labels and scores must be the same length")

    L = _as_logits(scores)
    g = _as_logits(context) if context is not None else np.zeros(len(labels), dtype=np.float64)

    b = _softmax(L)                                   # b_0: the feed-forward read
    initial = b.copy()
    trajectory = [float(b.max())]
    converged = False
    iterations = 0
    for t in range(max_iter):
        iterations = t + 1
        top_down = w_ctx * g + w_fb * np.log(b + _TINY)     # context + RECURRENT self-feedback
        b_new = _softmax(L + kappa * top_down)              # fold top-down onto the FIXED bottom-up evidence
        delta = float(np.abs(b_new - b).max())
        b = b_new
        trajectory.append(float(b.max()))
        if delta < eps:
            converged = True
            break

    confidence = float(b.max())
    initial_confidence = float(initial.max())
    delta_conf = confidence - initial_confidence
    winner = labels[int(np.argmax(b))]
    winner_initial = labels[int(np.argmax(initial))]
    flipped = winner != winner_initial

    # ---- honest verdict ---------------------------------------------------------------------------
    if not converged:
        status = "did_not_stabilize"          # ran out of budget while still moving — no victory declared
        resolved = False
        notes = (f"did not stabilise within {max_iter} iterations (still moving); reporting the "
                 f"honest interim confidence {confidence:.3f}, not a fabricated settled value")
    elif confidence < accept:
        status = "unresolved_ambiguous"       # settled, but the evidence+context could not disambiguate
        resolved = False
        notes = (f"converged to a STILL-AMBIGUOUS percept (confidence {confidence:.3f} < accept "
                 f"{accept}); evidence and context were insufficient — honest give-up, no confidence "
                 f"manufactured")
    elif delta_conf >= sharpen_margin or initial_confidence < accept:
        status = "sharpened"                  # started unsure, recurrence sharpened it to a usable percept
        resolved = True
        notes = (f"a low-confidence percept was recurrently SHARPENED {initial_confidence:.3f} -> "
                 f"{confidence:.3f} and stabilised" + (" (top-down context overrode the feed-forward "
                 "winner)" if flipped else ""))
    else:
        status = "confirmed"                  # already confident; recurrence confirmed it
        resolved = True
        notes = f"an already-confident percept ({initial_confidence:.3f}) was confirmed and stabilised"

    return RefinementTrace(
        labels=labels, initial=[float(x) for x in initial], final=[float(x) for x in b],
        trajectory=trajectory, winner=winner, winner_initial=winner_initial,
        confidence=confidence, initial_confidence=initial_confidence, delta_confidence=delta_conf,
        iterations=iterations, converged=converged, resolved=resolved, flipped=flipped,
        status=status, notes=notes)


def refine_with_plausibility(labels: Sequence[str], scores: Sequence[float], **kw) -> RefinementTrace:
    """Convenience: refine a detection using the perception plausibility organ as the top-down prior."""
    return refine(labels, scores, context=plausibility_prior(labels), **kw)


# ── neuro-ledger self-registration (mirrors the deliberator pattern) ─────────────────────────────
def ledger_entry():
    """This organ's honest ledger row: a ZERO-parameter, non-fact-source perception control organ.

    KAPPA/W_CTX/W_FB/ACCEPT are curated dynamical set-points (the homeostasis-set-point category),
    not weights fit to data — there is no artifact on disk and no learned count. Registered so the
    neuro budget audit accounts for it (fact_source=False, enforced=False, 0 params)."""
    from packages.neuro_ledger.ledger import Organ
    return Organ(
        id="perception_recurrence",
        path="packages/perception_recurrence/refinement.py",
        role="within-percept recurrent refinement: folds a top-down context prior (scene/plausibility "
             "expectation) back onto FIXED bottom-up detector evidence in a bounded fixed-point loop, "
             "sharpening a low-confidence percept until it stabilises — or honestly giving up (no "
             "confidence fabricated) when evidence+context are insufficient. ZERO learned weights "
             "(curated dynamical set-points, sub-critical self-feedback gain); never a fact source",
        gate="perception within-percept recurrence (RPT-1 consciousness_audit indicator) behind the "
             "plausibility top-down prior + the honest give-up gate (flat input -> uniform fixed point, "
             "so no certainty is manufactured)",
        artifacts=[],                    # no weight artifacts — a fixed-point iteration over curated constants
        fact_source=False,               # INVARIANT: a perceptual refiner proposes/settles, never asserts facts
        enforced=False,                  # control/perception tier: zero budget impact
        status="active",
        fallback_params=0,               # honest count: 0 trained parameters
    )


__all__ = ["RefinementTrace", "refine", "refine_with_plausibility", "plausibility_prior", "ledger_entry",
           "KAPPA", "W_CTX", "W_FB", "MAX_ITER", "EPS", "ACCEPT", "SHARPEN_MARGIN"]
