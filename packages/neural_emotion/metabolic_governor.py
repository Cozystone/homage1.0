# -*- coding: utf-8 -*-
"""Metabolic governor — the hormone field as the WHOLE organism's continuous regulator.

Owner (2026-07-20): the hormones should structurally govern the entire metabolism even without
consciousness, and it must be a real, finely-made organ — meaningful and fine-grained like a human's,
not decorative. The biology this mirrors: endocrine signalling is not a mood display, it is the
body's global resource-allocation protocol — cortisol mobilizes and defers non-essentials, thyroid
sets basal rate, insulin routes energy, and every tissue reads the SAME blood.

Here, every subsystem reads the SAME field (the 7-axis Neuromodulators) through this governor, which
derives a continuous metabolic REGIME — smooth functions of the axes, no if/else mood buckets
(fine-grained by construction: a small hormonal change makes a small regime change). The regime's
knobs are the organism's real levers:

  learning_rate_scale     how hard to learn right now   (acetylcholine-led; collapses under cortisol
                                                         — reuses rl_params, the anti-gaming collapse)
  exploration_temperature how widely to search           (noradrenaline lowers it: aroused = focused)
  load_shedding           how much heavy work to defer   (cortisol-led: stress sheds non-essentials)
  consolidation_pressure  how strongly to rest/consolidate (endorphin+serotonin high, arousal low
                                                         — the sleep-phase signal for D1)
  social_gain             how strongly to prioritize the person present (oxytocin)
  repair_priority         how urgently to run integrity/self-repair     (cortisol × sustained load)

Anti-wireheading invariant holds: the regime MODULATES work; no subsystem is rewarded for moving
hormones. Honest line: metabolic control, measured — no consciousness claim.
"""
from __future__ import annotations

from typing import Any


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def regime(levels: dict[str, float]) -> dict[str, float]:
    """The continuous metabolic regime read off the REAL hormone field. Pure, smooth, total."""
    dopa = float(levels.get("dopamine", 0.0))
    sero = float(levels.get("serotonin", 0.55))
    nora = float(levels.get("noradrenaline", 0.0))
    acet = float(levels.get("acetylcholine", 0.40))
    cort = float(levels.get("cortisol", 0.0))
    oxy = float(levels.get("oxytocin", 0.0))
    endo = float(levels.get("endorphin", 0.0))

    # learning: acetylcholine leads (encoding readiness), dopamine adds drive, cortisol collapses it
    lr = _clamp01(0.5 * acet + 0.35 * dopa) * _clamp01(1.0 - 0.6 * cort)
    # exploration: calm = broad search; phasic arousal narrows to the matter at hand, and chronic
    # stress narrows it too (the well-replicated stress->exploitation shift), reward tone widens it
    temperature = _clamp01(0.85 - 0.5 * nora - 0.25 * cort + 0.15 * dopa)
    # load shedding: stress defers the non-essential, smoothly (0.4 cort -> shed ~a third)
    shed = _clamp01(0.85 * cort)
    # consolidation: restfulness (endorphin, serotonin above its 0.55 baseline) with LOW arousal
    consolidation = _clamp01((0.5 * endo + 0.6 * max(0.0, sero - 0.55)) * (1.0 - 0.7 * nora)
                             * (1.0 - 0.5 * cort))
    # social: the person present amplifies attending to them
    social = _clamp01(0.9 * oxy)
    # repair: chronic load makes self-maintenance the first job
    repair = _clamp01(0.7 * cort + 0.2 * max(0.0, 0.55 - sero))

    return {
        "learning_rate_scale": round(lr, 3),
        "exploration_temperature": round(temperature, 3),
        "load_shedding": round(shed, 3),
        "consolidation_pressure": round(consolidation, 3),
        "social_gain": round(social, 3),
        "repair_priority": round(repair, 3),
    }


def governs(levels: dict[str, float], job_kind: str) -> dict[str, Any]:
    """Should this job run NOW, and how? The single question every subsystem asks the governor.
    job_kind: 'learn' | 'explore' | 'heavy' (bulk/mining) | 'consolidate' | 'respond' | 'repair'."""
    r = regime(levels)
    allow, scale = True, 1.0
    if job_kind == "learn":
        scale = r["learning_rate_scale"]
        allow = scale > 0.08                       # the anti-gaming collapse: near-zero lr = do not train
    elif job_kind == "heavy":
        allow = r["load_shedding"] < 0.55          # stressed organisms shed bulk work
        scale = 1.0 - r["load_shedding"]
    elif job_kind == "explore":
        scale = r["exploration_temperature"]
    elif job_kind == "consolidate":
        allow = r["consolidation_pressure"] > 0.25
        scale = r["consolidation_pressure"]
    elif job_kind == "respond":
        scale = 0.6 + 0.4 * r["social_gain"]       # always allowed; a person present amplifies it
    elif job_kind == "repair":
        allow = True
        scale = 0.4 + 0.6 * r["repair_priority"]
    return {"allow": allow, "scale": round(scale, 3), "regime": r}
