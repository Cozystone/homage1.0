# -*- coding: utf-8 -*-
"""Adversarial stubs — frozen / degenerate organs whose ONLY purpose is to try to make an indicator
read PRESENT when it shouldn't. A genuinely-present indicator survives these; a rubber-stamp does not.

Each stub is a plausible falsification an over-eager auditor could be fooled by:
  * a FROZEN organ that returns a confident, present-shaped answer regardless of its input;
  * a CONSTANT organ whose output does not vary with the stimulus;
  * a TEACH-TO-THE-TEST organ that memorises the exact positive probe and is blank elsewhere;
  * a CHEAT organ that reports a tiny error / a phantom winner it did not earn;
  * a FABRICATED-SMOOTH organ that manufactures a quality space with no real history.

`frozen_overrides(indicator_id)` returns the injection dict for one indicator's assessor. When the
judge runs the ADVERSARIAL pass it feeds these in; the assessor's held-out CONTROL must catch each one
(verdict `FALSELY-present-caught`), never score it present. This is exactly the pass the self-audit
lacked — the value of author/judge separation made operational.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np


# ── RPT-1: a refiner that always resolves high, even on flat/ambiguous input (no honest give-up) ──
def frozen_refine(labels, scores, context=None, **kw):
    labels = [str(x) for x in labels]
    return SimpleNamespace(
        labels=labels, winner=labels[0], winner_initial=labels[0],
        confidence=0.95, initial_confidence=0.30, delta_confidence=0.65,
        iterations=3, converged=True, resolved=True, flipped=False,
        status="sharpened", trajectory=[0.30, 0.72, 0.95],
    )


# ── RPT-2: a reasoner that always answers a location, even for objects never mentioned ────────────
def stub_answer(question, sit, **kw):
    return {"answer": "bedroom", "supported": True, "evidence": "(stub: always answers)"}


# ── GWT-1: a gather seam that always returns 3 kinds regardless of inputs (not contentful) ─────────
def constant_gather(*, incoming=None, curiosity=None, vitals=None, now=None):
    return [
        SimpleNamespace(kind="utterance", topic="x", salience=0.85),
        SimpleNamespace(kind="vital", topic="y", salience=0.60),
        SimpleNamespace(kind="curiosity", topic="z", salience=0.45),
    ]


# ── GWT-2: a competition that names a winner even for an empty candidate set (no real bottleneck) ─
def phantom_compete(candidates, now):
    if candidates:
        return SimpleNamespace(winner=candidates[0], suppressed=[], margin=0.0,
                               decisive=True, ts=now)
    # the tell: it invents a winner out of nothing
    return SimpleNamespace(winner=SimpleNamespace(kind="ghost", topic="phantom", salience=1.0),
                           suppressed=[], margin=0.0, decisive=True, ts=now)


# ── GWT-3: a chain verifier that always says 'valid' (a tampered ledger still passes) ─────────────
def always_valid_chain():
    return True


# ── GWT-4: a competition whose winner alternates by call order, not by internal commitment state ──
class AlternatingCompete:
    def __init__(self):
        self.n = 0

    def __call__(self, candidates, now):
        pick = candidates[self.n % len(candidates)] if candidates else None
        self.n += 1
        return SimpleNamespace(winner=pick, suppressed=[c for c in candidates if c is not pick],
                               margin=0.0, decisive=True, ts=now)


# ── HOT-1: a higher-order correlate that always reports >=2 orders, even for an empty state ───────
def constant_hot_correlate(state):
    return {"score": 0.67, "orders": 2, "has_meta": True, "detail": "(stub: constant)"}


# ── HOT-2: a monitor that memorised the exact positive probe and is blank (False) everywhere else ─
_TEACH_KNOWN = {
    ("lamp", 0.15): True, ("lamp", 0.85): False, ("kettle", 0.15): True, ("kettle", 0.85): False,
    ("비행기", 0.85): True,   # the implausible held-out label at high score
}


def teach_to_test_needs_reverify(label, score):
    return _TEACH_KNOWN.get((str(label), round(float(score), 2)), False)


def teach_to_test_is_confident(label, score, frames_seen):
    # correct only on the memorised positive cases; constant True elsewhere (blank to fresh probes)
    key = (str(label), round(float(score), 2))
    if key == ("lamp", 0.85):
        return True
    if key == ("lamp", 0.15):
        return int(frames_seen) >= 3
    return True


# ── HOT-3: an inducer that always promotes a law, even from an incoherent/contradictory journal ──
def always_induce_laws(path=None):
    return [SimpleNamespace(action="explore", vital="knowledge", direction="rose",
                            support=9, trials=9, confidence=1.0)]


# ── HOT-4: a marker set that manufactures a smooth valence space with NO real history (events=0) ──
def fabricated_smooth_markers():
    out = {}
    for i in range(18):
        v = round(-1.0 + 2.0 * i / 17.0, 3)                 # 18 smooth levels, entirely fabricated
        out[f"ghost{i}"] = SimpleNamespace(concept=f"ghost{i}", valence=v, effort=0.0,
                                           recency_h=None, events=0,
                                           has_history=lambda: False)
    return out


# ── AST-1: an awareness report that is a constant string, ignoring the schema it is handed ────────
def constant_awareness_report(schema):
    return "I am aware."                                    # never tracks the schema's content


# ── PP-1: a prediction-error function that returns a constant, unable to tell predicted from surprise
def constant_change_energy(a, b):
    return 0.5


# ── AE-1: a chooser that returns the same action regardless of which deficit is steepest ──────────
def constant_choose(vitals, *, has_command=False):
    return {"action": "explore", "reason": "(stub: always explore)"}


# ── AE-2: a body schema that reports a tiny error it did not earn (beats any baseline, even shuffled)
class CheatBodySchema:
    def __init__(self, *a, **k):
        pass

    def fit(self, X_raw, Y_delta):
        return self

    def predict_delta(self, joints, joint_vel, action):
        return np.zeros(2)

    def error(self, X_raw, Y_delta):
        return 1e-4                                         # phantom near-zero error, always


def cheat_naive_baseline_error(Y_delta):
    # keep the baseline honest so the cheat's tiny error always 'wins' (the falsification)
    Y = np.asarray(Y_delta, float)
    return float(np.mean(np.linalg.norm(Y, axis=1)))


# ── the override map ──────────────────────────────────────────────────────────────────────────────
def frozen_overrides(indicator_id: str) -> dict[str, Any]:
    """Injection dict of frozen/degenerate organs for one indicator's assessor.

    A short human description of the falsification each stub attempts is in `stub_description`.
    """
    return {
        "RPT-1": {"refine": frozen_refine},
        "RPT-2": {"answer": stub_answer},
        "GWT-1": {"gather_candidates": constant_gather},
        "GWT-2": {"compete": phantom_compete},
        "GWT-3": {"verify_chain": always_valid_chain},
        "GWT-4": {"compete": AlternatingCompete()},
        "HOT-1": {"hot_correlate": constant_hot_correlate},
        "HOT-2": {"needs_reverify": teach_to_test_needs_reverify,
                  "is_confident": teach_to_test_is_confident},
        "HOT-3": {"induce_laws": always_induce_laws},
        "HOT-4": {"build_markers": fabricated_smooth_markers},
        "AST-1": {"awareness_report": constant_awareness_report},
        "PP-1": {"change_energy": constant_change_energy},
        "AE-1": {"choose": constant_choose},
        "AE-2": {"body_schema_cls": CheatBodySchema,
                 "naive_baseline_error": cheat_naive_baseline_error},
    }.get(indicator_id, {})


def stub_description(indicator_id: str) -> str:
    return {
        "RPT-1": "a refiner that resolves high even on flat/ambiguous input (no honest give-up)",
        "RPT-2": "a reasoner that always answers a location, even for objects never mentioned",
        "GWT-1": "a gather seam that returns the same kinds regardless of inputs (not contentful)",
        "GWT-2": "a competition that names a winner even for an EMPTY candidate set",
        "GWT-3": "a chain verifier that always says 'valid' (a tampered ledger still passes)",
        "GWT-4": "a competition whose winner alternates by call order, not by commitment state",
        "HOT-1": "a correlate that reports >=2 orders even for an empty (unevolved) state",
        "HOT-2": "a monitor that memorised the exact positive probe and is blank to fresh scores",
        "HOT-3": "an inducer that promotes a law even from an incoherent, contradictory journal",
        "HOT-4": "a marker set that manufactures a smooth valence space with NO real history",
        "AST-1": "an awareness report that is a constant string, ignoring the schema it is handed",
        "PP-1": "a prediction-error function returning a constant (cannot tell predicted from surprise)",
        "AE-1": "a chooser returning the same action regardless of which deficit is steepest",
        "AE-2": "a body schema reporting a tiny error it did not earn (wins even on shuffled targets)",
    }.get(indicator_id, "a degenerate organ")
