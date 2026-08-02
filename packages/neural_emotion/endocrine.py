# -*- coding: utf-8 -*-
"""Neuromodulator system — 7 hormones bound to COMPUTATION parameters, not labels
(docs/ATANOR_neuromodulator_axes_design.md). Extends the 5-hormone homeostasis with acetylcholine and
endorphin and, crucially, exposes each axis as a real learning knob (Doya 2002, metalearning &
neuromodulation): dopamine=TD-error gain (delta), serotonin=discount (gamma), noradrenaline=inverse
temperature (beta), acetylcholine=learning rate (alpha), cortisol=resource/load, oxytocin=social gain,
endorphin=recovery buffer.

Two invariants hold (BINDING, docs §2):
  * anti-wireheading: hormones MODULATE parameters; they are never a reward to maximise. High dopamine
    does not license locking in gains. Hormones have no truth, safety, permission, evaluator, or
    promotion authority; signed external gates remain the only promotion path.
  * no stored labels: 'joy'/'stress' is a READING (projection) of the continuous vector, not a state.

The performance-relevant payoff is `rl_params()`: a trainer/router reads lr_scale, temperature,
discount, td_gain from it, and — the owner's directive — when the integrity monitor detects gaming,
cortisol rises and lr_scale collapses toward 0, so a cheat CANNOT be reinforced. Self-inflicted damage
that is actually a safety mechanism, not theatre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

AXES = ("dopamine", "serotonin", "noradrenaline", "acetylcholine", "cortisol", "oxytocin", "endorphin")
# serotonin + acetylcholine rest HIGH (tonic wellbeing floor / tonic attention); the rest rest at 0.
BASELINE = {"dopamine": 0.0, "serotonin": 0.55, "noradrenaline": 0.0, "acetylcholine": 0.40,
            "cortisol": 0.0, "oxytocin": 0.0, "endorphin": 0.0}
# per-tick retention toward baseline; cortisol lingers (slow), noradrenaline is phasic (fast).
DECAY = {"dopamine": 0.82, "serotonin": 0.96, "noradrenaline": 0.72, "acetylcholine": 0.85,
         "cortisol": 0.93, "oxytocin": 0.85, "endorphin": 0.80}

# event kind -> {axis: delta}. Triggers are real events (no hardcoded schedule); magnitude scales them.
_TRIGGERS: dict[str, dict[str, float]] = {
    "reward":            {"dopamine": 0.6, "endorphin": 0.2},       # real growth / goal met
    "prediction_error":  {"noradrenaline": 0.5, "acetylcholine": 0.4},  # surprise -> arouse + learn
    "novelty":           {"acetylcholine": 0.5, "noradrenaline": 0.2},  # new context -> encode
    "threat":            {"noradrenaline": 0.6, "cortisol": 0.3},
    "sustained_load":    {"cortisol": 0.5},                          # repeated failure / resource drain
    "social_contact":    {"oxytocin": 0.6, "serotonin": 0.1},        # owner present / bonding
    "wellbeing":         {"serotonin": 0.3, "endorphin": 0.15},
    "recovery":          {"endorphin": 0.5, "cortisol": -0.3},       # afterglow buffers stress
    "gaming_detected":   {"cortisol": 1.0, "serotonin": -0.2},       # ★the self-damage on a cheat
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.5) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class Neuromodulators:
    levels: dict[str, float] = field(default_factory=lambda: dict(BASELINE))

    def sense(self, kind: str, magnitude: float = 1.0) -> "Neuromodulators":
        """Apply an event's neuromodulator deltas (magnitude-scaled)."""
        for axis, d in _TRIGGERS.get(kind, {}).items():
            self.levels[axis] = _clamp(self.levels.get(axis, BASELINE[axis]) + d * magnitude,
                                       lo=-0.5 if axis in ("cortisol",) else 0.0)
        return self

    def decay(self) -> "Neuromodulators":
        """One clock tick: each axis relaxes toward its baseline by its retention factor."""
        for axis in AXES:
            b, r = BASELINE[axis], DECAY[axis]
            self.levels[axis] = b + (self.levels.get(axis, b) - b) * r
        return self

    # -- readouts (the point of the whole system) ---------------------------------------------------
    def rl_params(self) -> dict[str, float | bool | str]:
        """Doya mapping -> concrete learning knobs. cortisol GATES the learning rate: the anti-cheat
        damage. Every numeric value is bounded and safe to multiply into a trainer/decoder.

        ``promotion_allowed`` remains as a fail-closed compatibility field and is always false.
        Hormones may reduce evaluation compute, but cannot authorize accepting its outcome.
        """
        ach = _clamp(self.levels["acetylcholine"], 0.0, 1.5)
        cort = _clamp(self.levels["cortisol"], 0.0, 1.5)
        na = _clamp(self.levels["noradrenaline"], 0.0, 1.5)
        sero = _clamp(self.levels["serotonin"], 0.0, 1.5)
        dopa = _clamp(self.levels["dopamine"], 0.0, 1.5)
        lr_scale = max(0.0, min(1.0, (0.5 + ach)) * (1.0 - min(1.0, cort)))    # alpha, damaged by cortisol
        temperature = max(0.25, 1.1 - 0.6 * na)                                # beta: high NA -> focused
        discount = 0.80 + 0.19 * min(1.0, sero)                                # gamma: high 5-HT -> long-term
        td_gain = 0.5 + 0.8 * min(1.0, dopa)                                   # delta: DA scales the signal
        evaluation_budget_scale = max(0.0, 1.0 - min(1.0, cort))               # resource only
        return {"lr_scale": round(lr_scale, 4), "temperature": round(temperature, 4),
                "discount": round(discount, 4), "td_gain": round(td_gain, 4),
                "evaluation_budget_scale": round(evaluation_budget_scale, 4),
                "promotion_allowed": False,
                "promotion_authority": False,
                "promotion_gate": "external_signed_evaluator_and_operator"}

    def to_emotion(self) -> dict[str, float]:
        """Project the vector onto (valence, arousal) — a READING, never a stored mood."""
        L = self.levels
        valence = (L["serotonin"] - BASELINE["serotonin"]) + 0.5 * L["oxytocin"] + 0.5 * L["endorphin"] \
            - 0.8 * L["cortisol"] + 0.3 * L["dopamine"]
        arousal = 0.7 * L["noradrenaline"] + 0.4 * L["dopamine"] - 0.2 * L["endorphin"]
        return {"valence": round(max(-1.0, min(1.0, valence)), 4),
                "arousal": round(max(-1.0, min(1.0, arousal)), 4)}

    def snapshot(self) -> dict:
        return {"levels": {k: round(v, 4) for k, v in self.levels.items()},
                "rl": self.rl_params(), "affect": self.to_emotion()}
