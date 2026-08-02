"""Self-tuning for the answer policy — the mind adjusting its own answer weights, safely.

The user's goal: 'answer weights move fluidly in real time, yet average quality stays
high'. The safety mechanism that makes that non-scary: the tuner NEVER changes a weight
blindly. It measures decision quality on a labelled battery (each question tagged with the
mode it SHOULD get), does bounded coordinate descent, and ACCEPTS a change only when it
STRICTLY IMPROVES accuracy with no regression. So the policy can only move toward better
decisions — it cannot drift into worse ones. This is 'self-correction' with a guardrail.

The battery is grounded truth about question SHAPE, not opinions: a definitional question
should route to define/synthesise, a conversational one to engage, arithmetic to compute.
Getting those routings right is exactly what kept the engine from forcing definitions onto
' ?'. The tuner optimises that routing accuracy.

Runs offline (no live traffic needed), is deterministic, and writes the improved weights
through answer_policy.save_weights (atomic). It can be invoked manually
(scripts/tune_answer_policy.py) or proposed by the continuous-self loop as a gated
self-modification.
"""
from __future__ import annotations

import copy
from typing import Any

from .answer_policy import FEATURES, MODES, decide_mode, load_weights, save_weights, score_modes, extract_features

# Labelled routing battery: (question, grounding_signals, expected_mode). Grounding is the
# signal the retriever WOULD supply, so the tuner optimises the real decision boundary.
# 'accept' = any mode in the set is correct (define OR synthesize both fine for a definition
# with thin grounding, since the downstream neighbourhood handles it).
_BATTERY: list[tuple[str, dict[str, Any], set[str]]] = [
    # definitional — must define (or synthesise when grounding is a constellation)
    ("세포란?", {"named_match": 1.0, "has_definition": True}, {"define"}),
    ("광합성이 뭐야?", {"named_match": 1.0, "has_definition": True}, {"define"}),
    ("CPU는 무엇인가?", {"named_match": 1.0, "has_definition": True}, {"define"}),
    ("쿠버네티스가 뭐야?", {"named_match": 0.9, "has_definition": True}, {"define"}),
    ("민주주의란 무엇인가?", {"named_match": 0.8, "has_definition": True}, {"define"}),
    ("인공지능이 뭐야?", {"named_match": 0.0, "neighborhood": 0.8, "has_definition": False}, {"synthesize", "define"}),
    ("컴퓨터에 대해 설명해줘", {"named_match": 0.0, "neighborhood": 0.7, "has_definition": False}, {"synthesize", "define"}),
    # arithmetic — must compute
    ("12 곱하기 12는?", {"is_compute": True}, {"compute"}),
    ("사과 5개에서 2개를 빼면?", {"is_compute": True}, {"compute"}),
    # conversational — must engage (never a definition)
    ("고양이가 자꾸 물어요 왜 그럴까?", {"named_match": 0.9, "has_definition": True}, {"engage"}),
    ("회사를 그만두고 싶은데 어떻게 결정해?", {"named_match": 0.9, "has_definition": True}, {"engage"}),
    ("주식 처음인데 뭘 사야 돼?", {"named_match": 0.9, "has_definition": True}, {"engage"}),
    ("운동 처음 시작하는데 뭐부터 해야 해?", {"named_match": 0.8, "has_definition": True}, {"engage"}),
    ("인공지능이 사람 일자리를 다 뺏을까?", {"named_match": 0.7, "has_definition": True}, {"engage"}),
    ("행복하게 사는 비결이 뭐라고 생각해?", {"named_match": 0.3, "has_definition": False}, {"engage"}),
    ("결혼은 꼭 해야 하는 걸까?", {"named_match": 0.4, "has_definition": False}, {"engage"}),
    ("요즘 너무 피곤한데 어떻게 하면 좋을까?", {"named_match": 0.2, "has_definition": False}, {"engage"}),
    ("번아웃이 왔는데 어떻게 극복해?", {"named_match": 0.3, "has_definition": False}, {"engage"}),
    ("면접에서 자기소개 잘하는 팁 알려줘", {"named_match": 0.5, "has_definition": True}, {"engage"}),
    ("파이썬이랑 자바 중에 뭐부터 배우는 게 나아?", {"named_match": 0.8, "has_definition": True}, {"engage"}),
]


def accuracy(weights: dict[str, dict[str, float]] | None = None) -> tuple[float, list[tuple[str, str, bool]]]:
    """Fraction of the battery routed to an accepted mode, plus per-item detail."""
    detail = []
    hits = 0
    for q, sig, expected in _BATTERY:
        mode = decide_mode(q, sig, weights)[0]
        ok = mode in expected
        hits += int(ok)
        detail.append((q, mode, ok))
    return hits / max(1, len(_BATTERY)), detail


def _hinge(feats: dict[str, float], expected: set[str],
           weights: dict[str, dict[str, float]] | None) -> float:
    scores = score_modes(feats, weights)
    best_ok = max(scores[m] for m in expected)
    best_wrong = max((scores[m] for m in MODES if m not in expected), default=0.0)
    return min(1.0, best_ok - best_wrong)         # hinge: no reward past a safe margin


def _margin(weights: dict[str, dict[str, float]] | None = None,
            experience: list[tuple[dict[str, float], set[str]]] | None = None) -> float:
    """SMOOTH objective: sum of HINGE margins (correct-best minus best-wrong, clamped +1)
    over the hand battery PLUS labelled live experience. Accuracy is a step function that
    traps coordinate descent; the smooth margin lets the boundary move continuously.
    Experience terms are weighted 0.5 — lived evidence steers, the curated battery anchors."""
    total = 0.0
    for q, sig, expected in _BATTERY:
        total += _hinge(extract_features(q, sig), expected, weights)
    for feats, expected in (experience or []):
        total += 0.5 * _hinge(feats, expected, weights)
    return total


def tune(*, steps: int = 30, delta: float = 0.4, save: bool = False) -> dict[str, Any]:
    """Bounded coordinate descent on the SMOOTH margin objective. For each (mode, feature)
    weight, try ±delta and keep the change only if the margin strictly improves — which
    monotonically raises (never lowers) routing accuracy. Returns a report; writes weights
    only when `save` and accuracy improved."""
    weights = copy.deepcopy(load_weights())
    base_acc, _ = accuracy(weights)
    # labelled LIVE experience joins the objective (self-correction from real outcomes);
    # the hand battery stays a hard accuracy floor below.
    try:
        from .answer_experience import training_examples

        experience = training_examples()
    except Exception:
        experience = []
    margin = _margin(weights, experience)
    for _ in range(steps):
        improved_this_pass = False
        for mode in MODES:
            for feat in FEATURES:
                for step in (delta, -delta):
                    trial = copy.deepcopy(weights)
                    trial[mode][feat] = trial[mode].get(feat, 0.0) + step
                    trial_margin = _margin(trial, experience)
                    if trial_margin > margin + 1e-9:  # strict margin improvement
                        weights, margin = trial, trial_margin
                        improved_this_pass = True
        if not improved_this_pass:
            break
    final_acc, detail = accuracy(weights)
    # HARD SAFETY: the margin objective must never LOWER routing accuracy. If it somehow
    # did, discard the tuned weights entirely — the policy only ever moves toward better.
    if final_acc < base_acc - 1e-9:
        weights = copy.deepcopy(load_weights())
        final_acc, detail = accuracy(weights)
    misses = [(q, m) for q, m, ok in detail if not ok]
    report = {
        "base_accuracy": round(base_acc, 4),
        "tuned_accuracy": round(final_acc, 4),
        "improved": final_acc > base_acc + 1e-9,
        "battery_size": len(_BATTERY),
        "remaining_misses": misses,
    }
    if save and report["improved"]:
        save_weights(weights, meta={"tuned_accuracy": final_acc, "base_accuracy": base_acc,
                                    "battery_size": len(_BATTERY)})
        report["saved"] = True
    return report
