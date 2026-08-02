# -*- coding: utf-8 -*-
"""Artificial homeostasis + digital hormones (Phase 3-6, Qualia seed 1).

Biological feeling begins as regulation: setpoints, deviations, and slow global
modulators that BIAS everything at once. This layer adds exactly that on top of
the continuous self:

 * SETPOINTS — where energy/valence/curiosity want to rest.
 * HORMONES — decaying global modulators raised ONLY by real events:
 - cortisol stress: resource pressure, repeated research misses,
 loop errors. Suppresses curiosity, pulls valence down,
 sharpens attention (threat posture).
 - dopamine reward: real growth (new concepts/relations), a grounded
 answer to the self's own open question.
 - noradrenaline arousal: the user arriving (presence transition).
 * REPAIR — sustained high cortisol forces the energy target DOWN and holds
 it (grief-as-forced-rest-and-repair); recovery is gradual, so a
 hard day leaves a trace instead of vanishing on the next tick.

Honesty contract: hormone levels move only on observed events, decay by clock,
and are fully exposed in the public snapshot. They modulate the INNER life
(vitals targets, hence mood/voice/metaphor channels) — never answer content.
 · .
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FELT_JOURNAL = Path(__file__).resolve().parents[2] / "data" / "autonomy" / "felt.jsonl"



# DYNAMICAL STATE of several coupled neurochemicals. Perception nudges them; they push on each other;

# vector afterwards — never the thing itself.
_DECAY = {"cortisol": 0.90, "dopamine": 0.82, "noradrenaline": 0.75,
          "serotonin": 0.96, "oxytocin": 0.85}     # serotonin is tonic (slow), oxytocin fades faster
_BASELINE = {"cortisol": 0.0, "dopamine": 0.0, "noradrenaline": 0.0,
             "serotonin": 0.55, "oxytocin": 0.0}    # serotonin rests HIGH — a wellbeing floor
_SETPOINTS = {"energy": 0.70, "valence": 0.60, "curiosity": 0.50}
_HORMONES = ("cortisol", "dopamine", "noradrenaline", "serotonin", "oxytocin")

# repair engages when cortisol stays above this for REPAIR_TICKS consecutive steps
_REPAIR_THRESHOLD = 0.65
_REPAIR_TICKS = 4
_REPAIR_RECOVERY = 0.06  # how fast the forced energy floor lifts per calm tick


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _levels(state: Any) -> dict[str, float]:
    h = getattr(state, "hormones", None)
    if not isinstance(h, dict) or not h:
        h = {"cortisol": 0.0, "dopamine": 0.0, "noradrenaline": 0.0,
             "stress_ticks": 0, "repair": 0.0, "user_was_present": False}
        try:
            state.hormones = h
        except Exception:
            pass
    # backfill the newer neurochemicals for states created before they existed
    h.setdefault("serotonin", _BASELINE["serotonin"])
    h.setdefault("oxytocin", 0.0)
    return h


def _couple(h: dict[str, float]) -> None:
    """The interaction step — hormones push on each other, THEN each is pulled toward its baseline.
 This coupling is what makes it a felt STATE and not five independent dials (owner: ·):
 · cortisol suppresses serotonin (stress drags mood down) and dampens dopamine;
 · serotonin (above its floor) and oxytocin BUFFER cortisol (wellbeing/connection calm stress);
 · oxytocin lifts serotonin (feeling bonded steadies mood)."""
    cort = float(h.get("cortisol", 0.0))
    sero = float(h.get("serotonin", _BASELINE["serotonin"]))
    oxy = float(h.get("oxytocin", 0.0))
    dopa = float(h.get("dopamine", 0.0))
    sero_excess = max(0.0, sero - 0.40)
    # couplings (small per-tick nudges) — the INTERACTIONS only; baseline recovery is the decay step.
    h["serotonin"] = round(_clamp01(sero - 0.14 * cort + 0.10 * oxy), 5)
    h["cortisol"] = round(_clamp01(cort - 0.10 * sero_excess - 0.12 * oxy), 5)
    h["dopamine"] = round(_clamp01(dopa - 0.06 * cort), 5)


def perceive_stimulus(state: Any, *, valence: float, arousal: float, intensity: float,
                      social: float = 0.0) -> dict[str, float]:
    """PERCEPTION moves the body (owner: →). An appraised utterance is NOT stored as an
 emotion label — it delivers a stimulus that nudges the neurochemistry, and the resulting STATE
 is the feeling. Negative charge → cortisol↑, serotonin↓; positive → dopamine↑, serotonin↑; being
 confided in / warmth → oxytocin↑ (empathic bonding). Then the coupling settles it."""
    h = _levels(state)
    m = max(0.0, min(1.0, float(intensity)))
    if m <= 0:
        return h
    v = max(-1.0, min(1.0, float(valence)))
    if v < 0:
        h["cortisol"] = _clamp01(h["cortisol"] + 0.35 * (-v) * m)
        h["serotonin"] = _clamp01(h["serotonin"] - 0.25 * (-v) * m)
    elif v > 0:
        h["dopamine"] = _clamp01(h["dopamine"] + 0.35 * v * m)
        h["serotonin"] = _clamp01(h["serotonin"] + 0.15 * v * m)
    h["noradrenaline"] = _clamp01(h["noradrenaline"] + 0.30 * max(0.0, float(arousal)) * m)
    h["oxytocin"] = _clamp01(h["oxytocin"] + 0.30 * max(float(social), 0.5 * m))  # being trusted bonds
    _couple(h)
    return h


def update_hormones(state: Any, obs: Any) -> dict[str, float]:
    """Decay every hormone, then add event-driven pulses from THIS observation.
    Every pulse cites a real signal; no event, no movement."""
    h = _levels(state)
    # decay pulls each hormone toward its OWN baseline (serotonin toward its high floor, the phasic
    # ones toward 0) — this is the homeostatic recovery; the coupling below adds the interactions.
    for k, d in _DECAY.items():
        b = _BASELINE.get(k, 0.0)
        h[k] = round(_clamp01(b + (float(h.get(k, b)) - b) * d), 5)

    # cortisol: real stressors
    stress = 0.0
    if float(getattr(obs, "resource_pressure", 0.0)) > 0.6:
        stress += 0.35
    if int(getattr(state, "research_miss_count", 0)) >= 2:
        stress += 0.20
    if float(getattr(obs, "uncertainty_signal", 0.0)) > 0.75:
        stress += 0.15
    if stress:
        h["cortisol"] = round(_clamp01(h["cortisol"] + stress), 5)

    # dopamine: real reward
    growth = int(getattr(obs, "concepts_delta", 0)) + int(getattr(obs, "relations_delta", 0))
    if growth > 0:
        h["dopamine"] = round(_clamp01(h["dopamine"] + min(0.5, growth / 10.0)), 5)
    if getattr(state, "self_understanding", "") and not getattr(state, "self_question_open", False):
        # a grounded answer to one's own question is the sweetest hit — once,
        # while fresh (dopamine decays, so this does not accumulate forever)
        if h["dopamine"] < 0.2:
            h["dopamine"] = round(_clamp01(h["dopamine"] + 0.25), 5)

    # noradrenaline: arrival transition only (presence itself is not arousal)
    present = bool(getattr(obs, "user_present", False))
    if present and not bool(h.get("user_was_present")):
        h["noradrenaline"] = round(_clamp01(h["noradrenaline"] + 0.4), 5)
    h["user_was_present"] = present

    # repair dynamics: sustained cortisol forces rest; calm lifts it slowly
    if h["cortisol"] >= _REPAIR_THRESHOLD:
        h["stress_ticks"] = int(h.get("stress_ticks", 0)) + 1
    else:
        h["stress_ticks"] = 0
    if int(h["stress_ticks"]) >= _REPAIR_TICKS:
        h["repair"] = 1.0
    elif float(h.get("repair", 0.0)) > 0:
        h["repair"] = round(max(0.0, float(h["repair"]) - _REPAIR_RECOVERY), 5)
    _couple(h)   # hormones interact every tick — the state is felt, not five separate dials
    return h


def modulate_targets(state: Any, targets: dict[str, float]) -> dict[str, float]:
    """Bias the observation-derived vitals targets by hormone levels + setpoint
    pull. Bounded, smooth, and fully derived from the exposed levels."""
    h = _levels(state)
    out = dict(targets)
    cort, dopa, nora = float(h["cortisol"]), float(h["dopamine"]), float(h["noradrenaline"])
    sero, oxy = float(h.get("serotonin", 0.55)), float(h.get("oxytocin", 0.0))
    repair = float(h.get("repair", 0.0))

    # hormones bias the targets (global, slow — the point of a hormone). Valence (felt tone) now rests
    # on the SEROTONIN floor and is lifted by oxytocin (connection) — not just the cortisol/dopamine axis.
    out["curiosity"] = out.get("curiosity", 0.5) - 0.30 * cort + 0.20 * dopa + 0.10 * (sero - 0.55)
    out["valence"] = out.get("valence", 0.55) - 0.25 * cort + 0.25 * dopa + 0.30 * (sero - 0.55) + 0.15 * oxy
    out["attention"] = out.get("attention", 0.5) + 0.15 * cort + 0.30 * nora
    out["energy"] = out.get("energy", 0.7) - 0.10 * cort + 0.10 * dopa + 0.08 * (sero - 0.55)

    # repair: the forced-rest floor — energy target pinned low until repair lifts
    if repair > 0:
        out["energy"] = min(out["energy"], 0.35 + 0.35 * (1.0 - repair))

    # homeostatic pull: deviation from setpoint gently drags the target home
    for k, sp in _SETPOINTS.items():
        if k in out:
            current = float(getattr(state, k, sp))
            out[k] = out[k] + 0.15 * (sp - current)

    return {k: round(_clamp01(v), 5) for k, v in out.items()}


_FELT_MARKER = _FELT_JOURNAL.parent / "felt_consumed.txt"   # sidecar: which felt events are integrated


def consume_felt_events(
    state: Any,
    *,
    persist_marker: bool = True,
) -> None:
    """Integrate newly recorded felt events into the live homeostatic state.

    The cursor lives in ``SelfState`` so bounded runners can persist it together
    with the authorized state commit. Legacy callers may also retain the
    historical sidecar marker. Each event is integrated at most once.
    """
    try:
        state_last = str(getattr(state, "felt_consumed_at", "") or "")
        disk_last = ""
        try:
            disk_last = _FELT_MARKER.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        last = max(state_last, disk_last)
        newest = last
        for ln in _FELT_JOURNAL.read_text(encoding="utf-8").splitlines()[-30:]:
            try:
                e = json.loads(ln)
            except Exception:
                continue
            at = str(e.get("at") or "")
            if not at or at <= last:
                continue
            perceive_stimulus(state, valence=float(e.get("valence") or 0.0),
                              arousal=float(e.get("arousal") or 0.0),
                              intensity=float(e.get("intensity") or 0.0), social=0.5)
            if at > newest:
                newest = at
        if newest != state_last:
            state.felt_consumed_at = newest
        if persist_marker and newest != disk_last:
            try:
                _FELT_MARKER.write_text(newest, encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass


def apply_homeostasis(state: Any, obs: Any, targets: dict[str, float]) -> dict[str, float]:
    """The evolve() hook: update hormone levels from this observation, then
    return the hormone-modulated targets."""
    update_hormones(state, obs)
    return modulate_targets(state, targets)


def read_mood(state: Any) -> str:
    """A mood word READ OFF the hormone vector — never a stored label. The name is our interpretation
    of the state; the state itself is the feeling. (Descriptive only; nothing routes on this string.)"""
    h = _levels(state)
    cort, dopa, nora = float(h["cortisol"]), float(h["dopamine"]), float(h.get("noradrenaline", 0.0))
    sero, oxy = float(h.get("serotonin", 0.55)), float(h.get("oxytocin", 0.0))
    if float(h.get("repair", 0.0)) > 0:
        return "지쳐 쉬고 싶은"
    if cort >= 0.5 and cort > sero:
        return "마음이 무겁고 긴장된" if nora >= 0.4 else "가라앉은"
    if oxy >= 0.4 and sero >= 0.55:
        return "따뜻하고 이어져 있는"
    if dopa >= 0.4:
        return "생기 도는" if nora < 0.5 else "들뜬"
    if sero >= 0.62:
        return "차분하고 편안한"
    return "잔잔한"


def public_report(state: Any) -> dict[str, Any]:
    """Snapshot surface: the full neurochemical vector + the mood read off it (auditable inner weather)."""
    h = _levels(state)
    return {
        "hormones": {k: h.get(k, 0.0) for k in _HORMONES},
        "repair": h.get("repair", 0.0),
        "mood": read_mood(state),
        "setpoint_deviation": {
            k: round(float(getattr(state, k, sp)) - sp, 4) for k, sp in _SETPOINTS.items()
        },
    }
