# -*- coding: utf-8 -*-
"""allocator — the meta-greedy, depth-1, regress-free effort controller (NS-4 §4).

ONE dot product decides the next rung. No meta-plan, no meta-meta level — a reflex, exactly as the
research prescribes (Milli/Lieder/Griffiths 2017; Ackerman & Thompson 2017: the monitor is cheap and
heuristic on purpose). The value of the allocator is knowing when to STOP — because more thinking can
hurt (Inverse Scaling in Test-Time Compute, TMLR 2025).

    escalate_score = w · [ 1-felt_conf(FOR),  X1_compression_progress,  conflict,
                           abstain_margin,     difficulty_prior,         remaining_budget ]

Control loop (start at R0, climb at most to R2):
  * ESCALATE one rung when escalate_score > θ_hi AND budget remains  (meta-greedy: next rung yes/no).
  * SCHMITT TRIGGER — a hysteresis band [θ_lo, θ_hi]: only cross to "stop" below θ_lo, only cross to
    "escalate" above θ_hi; inside the band, hold the prior stance. Kills thrash (anti-oscillation).
  * MINIMUM-BLOCK REFRACTORY — a rung runs to completion (its whole minimum block of work) before the
    score is re-evaluated; the controller never interrupts a rung mid-flight.
  * DIMINISHING STOP-CRITERION (Ackerman 2014) — the bar to KEEP SPENDING rises as the budget burns
    (hi, lo both drift up with spent fraction), so the loop is GUARANTEED to terminate.
  * VERIFIER-GATED STOP — the one transferable lesson from o1/best-of-N: extra search is only worth it
    while the verifier improves. If an escalation does not raise the deliberator's grounding score, we
    stop and keep the BEST-VERIFIED answer (not the deepest). ATANOR's own verifier, no LLM.
  * FLOOR — if no rung grounds an answer, ABSTAIN. Never fabricate.

``w`` is a fixed, hand-set vector (below). In production it is OFFLINE-AMORTIZED (BMPS, UAI 2018):
log (features -> was-escalation-worth-it: did the deeper rung change the answer to a correct one?)
tuples and fit ``w`` by logistic regression / policy-gradient once, offline; runtime stays one dot
product. amortize_w() documents that fit; v1 ships the reasonable hand-set weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .ladder import RungResult, run_r0, run_r1, run_r2, ABSTAIN
from .signals import x1_voc, difficulty_prior


# ── the fixed weight vector (offline-amortizable) ────────────────────────────────────────────────
# Order: [inv_for, x1_voc, conflict, abstain_margin, difficulty_prior, remaining_budget].
# FOR dominates (Thompson 2011: the fluency/rightness feeling is what summons System-2). The VOC
# proxy, conflict and abstain-margin are the corroborating "more compute could help" signals; the
# difficulty prior is a weak shape hint; remaining_budget makes escalation cheaper early and self-
# throttling late. Sum ≈ 1 so escalate_score is ~[0,1] and the thresholds read as fractions.
DEFAULT_W: tuple[float, ...] = (0.40, 0.15, 0.15, 0.15, 0.10, 0.05)

_FEATURE_NAMES = ("inv_for", "x1_voc", "conflict", "abstain_margin", "difficulty_prior",
                  "remaining_budget")


@dataclass
class Features:
    inv_for: float
    x1_voc: float
    conflict: float
    abstain_margin: float
    difficulty_prior: float
    remaining_budget: float

    def vec(self) -> list[float]:
        return [self.inv_for, self.x1_voc, self.conflict, self.abstain_margin,
                self.difficulty_prior, self.remaining_budget]

    def as_dict(self) -> dict[str, float]:
        return {n: round(v, 4) for n, v in zip(_FEATURE_NAMES, self.vec())}


def escalate_score(feats: Features, w: tuple[float, ...] = DEFAULT_W) -> float:
    """The single meta-greedy dot product. Higher = more worth escalating a rung."""
    return float(sum(wi * fi for wi, fi in zip(w, feats.vec())))


@dataclass
class AllocatorConfig:
    theta_hi: float = 0.45          # escalate above this
    theta_lo: float = 0.30          # only cross to "stop" below this (Schmitt hysteresis)
    budget: float = 60.0            # hard budget in op-units
    diminish: float = 0.30          # how fast the stop-bar rises as budget burns (Ackerman)
    verifier_eps: float = 1e-6      # a rung must raise the verifier by more than this to justify itself
    w: tuple[float, ...] = DEFAULT_W


@dataclass
class AllocationTrace:
    answer: str | None
    grounded: bool
    abstained: bool
    rung_reached: str               # deepest rung actually run
    final_rung: str                 # rung whose answer was kept (verifier-gated)
    total_cost: float
    rungs: list[RungResult] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        for r in self.rungs:
            if r.rung == self.final_rung:
                return r.confidence
        return 0.0


# ── feature extraction from a rung result ────────────────────────────────────────────────────────

def _features_from(r: RungResult, query: Any, remaining_budget: float) -> Features:
    """Build the cheap feature vector from a rung's REAL signals. R0 exposes felt/conflict/abstain and
    a VOC library; a deliberator rung exposes only its verifier (its felt fields are empty), so we lean
    on its grounding there. All values in [0,1]."""
    felt = r.detail.get("felt", {}) if r.detail else {}
    for_conf = felt.get("for_conf", r.confidence)
    conflict = felt.get("conflict", 0.0 if r.grounded else 1.0)
    abstain_margin = felt.get("abstain_margin", 0.0 if r.grounded else 1.0)
    voc = x1_voc(r.answer_tree, r.voc_blocks)
    diff = difficulty_prior(getattr(query, "text", ""))
    return Features(
        inv_for=max(0.0, 1.0 - float(for_conf)),
        x1_voc=float(voc),
        conflict=float(conflict),
        abstain_margin=float(abstain_margin),
        difficulty_prior=float(diff),
        remaining_budget=max(0.0, min(1.0, float(remaining_budget))),
    )


# ── the controller ───────────────────────────────────────────────────────────────────────────────

class Allocator:
    """The metacognitive effort allocator. ``allocate(query)`` runs the rung ladder under the control
    loop and returns an AllocationTrace (answer + which rungs were spent + the decision log)."""

    def __init__(self, config: AllocatorConfig | None = None):
        self.cfg = config or AllocatorConfig()

    def allocate(self, query: Any, *, felt_context: Any = None) -> AllocationTrace:
        cfg = self.cfg
        rungs: list[RungResult] = []
        decisions: list[dict] = []

        # --- R0 is always run (the minimum block) ---
        r0 = run_r0(query, felt_context=felt_context)
        rungs.append(r0)
        spent = r0.cost
        escalating = False                      # Schmitt state: start stop-leaning

        climbers: list[Callable] = [run_r1, run_r2]
        best_ver = r0.verifier_score

        cur = r0
        for step, climb in enumerate(climbers):
            frac = min(1.0, spent / cfg.budget) if cfg.budget > 0 else 1.0
            feats = _features_from(cur, query, remaining_budget=1.0 - frac)
            score = escalate_score(feats, cfg.w)

            # diminishing stop-criterion: the bar to keep spending rises with the spent fraction
            hi = cfg.theta_hi + cfg.diminish * frac
            lo = cfg.theta_lo + cfg.diminish * frac

            # Schmitt trigger (hysteresis): flip to escalate only above hi, to stop only below lo
            if score > hi:
                escalating = True
            elif score < lo:
                escalating = False
            # inside [lo, hi]: hold prior stance

            budget_ok = (spent + 1.0) <= cfg.budget
            decision = {
                "from_rung": cur.rung, "considering": ("R1" if step == 0 else "R2"),
                "score": round(score, 4), "hi": round(hi, 4), "lo": round(lo, 4),
                "escalating": escalating, "budget_ok": budget_ok, "spent": round(spent, 2),
                "features": feats.as_dict(),
            }

            if not (escalating and budget_ok):
                decision["action"] = "STOP"
                decision["why"] = ("confident/settled — score below the (rising) stop bar"
                                   if not escalating else "budget exhausted")
                decisions.append(decision)
                break

            # --- escalate one rung (refractory: the whole rung runs before we re-evaluate) ---
            decision["action"] = "ESCALATE"
            nxt = climb(query, felt_context=felt_context)
            spent += nxt.cost
            rungs.append(nxt)

            # verifier-gated stop: did this rung actually improve grounding?
            improved = nxt.verifier_score > best_ver + cfg.verifier_eps
            decision["verifier_prev"] = round(best_ver, 4)
            decision["verifier_now"] = round(nxt.verifier_score, 4)
            decision["verifier_improved"] = improved
            decisions.append(decision)

            best_ver = max(best_ver, nxt.verifier_score)
            cur = nxt

            if nxt.grounded and not improved:
                decisions.append({"from_rung": nxt.rung, "action": "STOP",
                                  "why": "verifier did not improve — extra search not worth it; "
                                         "keep the best-verified answer"})
                break

        # --- verifier-gated FINAL choice: keep the best-verified GROUNDED answer, else ABSTAIN ---
        grounded_rungs = [r for r in rungs if r.grounded and r.answer is not None]
        if grounded_rungs:
            final = max(grounded_rungs, key=lambda r: r.verifier_score)
            return AllocationTrace(
                answer=final.answer, grounded=True, abstained=False,
                rung_reached=rungs[-1].rung, final_rung=final.rung,
                total_cost=round(spent, 2), rungs=rungs, decisions=decisions)

        return AllocationTrace(
            answer=None, grounded=False, abstained=True,
            rung_reached=rungs[-1].rung, final_rung="ABSTAIN",
            total_cost=round(spent, 2), rungs=rungs, decisions=decisions)


# ── offline amortization of w (documented; v1 ships hand-set weights) ─────────────────────────────

def amortize_w(log: list[tuple[list[float], int]], *, iters: int = 2000, lr: float = 0.1) -> list[float]:
    """Document + reference implementation of the OFFLINE weight fit (BMPS, UAI 2018). ``log`` is a
    list of (feature_vector, label) where label=1 iff escalating on that query WAS worth it (the deeper
    rung changed the answer to a correct one) and 0 otherwise. Fits ``w`` by logistic regression so
    escalate_score calibrates to P(escalation worth it). Runtime never calls this — it runs once,
    offline, and the resulting vector replaces DEFAULT_W. Pure numpy/stdlib.

    v1 ships the hand-set DEFAULT_W (a reasonable prior); this function is the amortization path the
    research names, provided so the wiring is honest and the upgrade is mechanical, not mythical."""
    import numpy as np
    if not log:
        return list(DEFAULT_W)
    X = np.array([f for f, _ in log], dtype=float)
    y = np.array([lab for _, lab in log], dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ w)))
        grad = X.T @ (p - y) / len(y)
        w -= lr * grad
    # clip to non-negative (every feature argues FOR escalation by construction) and renormalize
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return (w / s).tolist() if s > 0 else list(DEFAULT_W)
