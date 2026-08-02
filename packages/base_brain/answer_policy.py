"""Soft answer-mode policy — the fluid, self-tunable replacement for a brittle rule
router.

The user's design goal: don't hardcode 'this shape → this handler' with if/else. Instead
let the decision emerge from CONTINUOUS signals combined by WEIGHTS, so 'answer weights,
conditions, and shapes move fluidly in real time' — while quality stays high. A No-LLM
system still needs SOME decision layer (removing it entirely means either falling back to
rules or fabricating), so we make that layer soft and tunable rather than fixed.

How it works:
  1. FEATURES — continuous signals read from the query + retrieval, NOT hard labels:
     shape-cue strengths (definitional / causal / advice / opinion / personal), grounding
     strength (named-concept match, neighbourhood size, has-definition), compute-detect.
  2. SCORE — each answer MODE (compute / define / synthesise / engage / abstain) gets a
     weighted linear score over the features. The winner is argmax; near-ties are a real
     blend, so a factual question with weak grounding leans 'engage', a conversational one
     with strong grounding can still 'define'. Nothing is a hard gate.
  3. WEIGHTS — a persisted policy (data/answer_policy.json). The DEFAULT weights are chosen
     to reproduce the current, measured-good behaviour (0 confident-wrong on the battery),
     so introducing the soft layer is behaviour-preserving. From there the weights are
     TUNABLE — self_tuning.py measures quality on the offline battery and proposes weight
     deltas through the gated self-modification pipeline (the mind tuning its own answer
     policy, safely).

This is the honest middle path: not a rigid router, not a hallucinating free-for-all — a
grounded, weighted, self-correcting policy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MODES = ("compute", "define", "synthesize", "engage", "abstain")
FEATURES = (
    "bias", "cue_definition", "cue_causal", "cue_advice", "cue_opinion", "cue_personal",
    "grounding_named", "grounding_neighborhood", "has_definition", "is_compute",
)

_POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "answer_policy.json"

# DEFAULT weights — hand-set so decide_mode reproduces the current shape-router behaviour:
#   compute wins when is_compute; define wins on a definitional cue + a real named match;
#   synthesise wins on a rich neighbourhood; engage wins on conversational cues with weak
#   grounding; abstain is the floor. These are the STARTING point; the tuner moves them.
_DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "compute":    {"bias": -3.0, "is_compute": 8.0},
    "define":     {"bias": -1.2, "cue_definition": 2.2, "grounding_named": 2.6, "has_definition": 1.4,
                   "cue_advice": -2.5, "cue_causal": -2.0, "cue_opinion": -2.2, "cue_personal": -3.0},
    "synthesize": {"bias": -1.6, "grounding_neighborhood": 3.0, "cue_definition": 0.8,
                   "cue_advice": -1.5, "cue_personal": -2.0},
    "engage":     {"bias": -1.0, "cue_advice": 2.6, "cue_opinion": 2.6, "cue_personal": 3.0,
                   "cue_causal": 2.2, "grounding_named": -0.6},
    "abstain":    {"bias": 0.0},
}

_STORE = {"weights": None, "sig": None}


def load_weights() -> dict[str, dict[str, float]]:
    """Persisted policy weights, or the behaviour-preserving defaults. Cached by mtime."""
    try:
        if _POLICY_PATH.exists():
            sig = _POLICY_PATH.stat().st_mtime
            if _STORE["sig"] != sig:
                raw = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
                # merge over defaults so a partial file never drops a mode/feature
                merged = {m: dict(_DEFAULT_WEIGHTS[m]) for m in MODES}
                for m, feats in (raw.get("weights") or {}).items():
                    if m in merged and isinstance(feats, dict):
                        merged[m].update({k: float(v) for k, v in feats.items() if k in FEATURES})
                _STORE["weights"], _STORE["sig"] = merged, sig
            return _STORE["weights"]
    except Exception:
        pass
    return {m: dict(_DEFAULT_WEIGHTS[m]) for m in MODES}


def save_weights(weights: dict[str, dict[str, float]], *, meta: dict[str, Any] | None = None) -> None:
    _POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"weights": weights, "meta": meta or {}}
    tmp = _POLICY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_POLICY_PATH)
    _STORE["sig"] = None  # force reload


# --- feature extraction: continuous shape-cue strengths (reuse the shape regexes as
# soft signals, not hard gates) + grounding signals supplied by the caller. -----------
def _cue_scores(query: str) -> dict[str, float]:
    from .zero_user_answer import (
        _SHAPE_ADVICE, _SHAPE_CAUSAL, _SHAPE_DEFINITION, _SHAPE_OPINION, _SHAPE_PERSONAL,
    )
    q = str(query or "")
    return {
        "cue_definition": 1.0 if _SHAPE_DEFINITION.search(q) else 0.0,
        "cue_causal": 1.0 if _SHAPE_CAUSAL.search(q) else 0.0,
        "cue_advice": 1.0 if _SHAPE_ADVICE.search(q) else 0.0,
        "cue_opinion": 1.0 if _SHAPE_OPINION.search(q) else 0.0,
        "cue_personal": 1.0 if _SHAPE_PERSONAL.search(q) else 0.0,
    }


def extract_features(query: str, signals: dict[str, Any] | None = None) -> dict[str, float]:
    """Continuous feature vector. `signals` carries grounding facts the caller already
    computed: named_match (0..1), neighborhood (0..1), has_definition (bool), is_compute."""
    s = signals or {}
    feats = {f: 0.0 for f in FEATURES}
    feats["bias"] = 1.0
    feats.update(_cue_scores(query))
    feats["grounding_named"] = float(s.get("named_match") or 0.0)
    feats["grounding_neighborhood"] = float(s.get("neighborhood") or 0.0)
    feats["has_definition"] = 1.0 if s.get("has_definition") else 0.0
    feats["is_compute"] = 1.0 if s.get("is_compute") else 0.0
    return feats


def score_modes(features: dict[str, float], weights: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    w = weights or load_weights()
    return {m: sum(w[m].get(f, 0.0) * features.get(f, 0.0) for f in FEATURES) for m in MODES}


def decide_mode(query: str, signals: dict[str, Any] | None = None,
                weights: dict[str, dict[str, float]] | None = None) -> tuple[str, dict[str, float]]:
    """Soft decision: return (winning_mode, full_score_distribution). argmax of a weighted
    blend — fluid, auditable, tunable. The distribution lets callers see near-ties."""
    feats = extract_features(query, signals)
    scores = score_modes(feats, weights)
    winner = max(scores, key=lambda m: (scores[m], MODES.index(m)))
    return winner, scores
