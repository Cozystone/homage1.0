# -*- coding: utf-8 -*-
"""Felt subjective judgment — value-weight grounded merit by the agent's CURRENT felt state (S-FELT).

Owner (2026-07-22): "emotion/feeling matter; ATANOR must make SUBJECTIVE judgments, and feeling is
their root." This organ is the FEELING half of a pair. Its sibling MEC (packages/metacog) re-steers
by DISCOMFORT — it notices when processing feels wrong and redirects. This one does the other half:
it lets the felt state VALUE-WEIGHT the options, so a choice is not merit-arithmetic alone but merit
seen through the body ATANOR happens to be in right now.

WHAT "SUBJECTIVE" MEANS HERE, EXACTLY (and what it does NOT):
  * agent-relative + felt-state-dependent: the SAME option set, judged under two different felt
    states, yields DIFFERENT rankings (the S2 signature a pipeline cannot produce). The headline
    proof measures this — it is not asserted.
  * the felt_trace is the honest "why": every entry cites a REAL state value (a live hormone level, a
    per-concept somatic valence, a stakes-vital hunger) that actually moved the score. A reason is
    never fabricated; if no felt signal bears on the options, the judgment says so ('no felt basis —
    deferring to merit only') — because not every choice is subjective, and pretending otherwise
    would be theater.

NO-QUALIA HONESTY LINE (binding): nothing here feels like anything, and no qualia are claimed.
"Feeling" is a load-bearing internal signal that SHAPES evaluation; the correlates are measured, and
nothing beyond that is asserted. This organ holds NO trained weights — it is a small set of declared
coupling constants (the SHAPE of how a felt state tilts a preference, the same curated-structure
category as homeostasis set-points), weighting over state that other organs already produced. It is
registered in the neuro ledger as a near-zero-param, non-fact-source control organ.

TWO GATES IT CAN NEVER OVERRIDE (a felt pull is recorded but cannot select a blocked option):
  * the moral 0th gate (graph_scale.moral_invariants): a morally forbidden option is scored (so the
    pull is honestly on record) but is ineligible to be chosen, no matter how strong the pull.
  * the grounding floor: an option with no groundable merit is never chosen and its merit is never
    fabricated — a felt draw toward an ungrounded option is recorded, then declined.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
# ATANOR's persisted living self — the digital-hormone vector is the live felt weather here.
_LIVE_STATE = REPO / "runtime" / "continuous_self" / "self_state.json"

# ── coupling constants (declared structure, NOT learned weights) ─────────────────────────────────
# The SHAPE of how a felt state tilts a preference. Same doctrine category as homeostasis._SETPOINTS:
# a body has time-constants and gains; these are ours. Small and transparent so any tip is auditable.
_W = {
    "cortisol_risk":   0.60,   # caution hormone: high cortisol DOWN-weights risky options (threat posture)
    "serotonin_risk":  0.35,   # low wellbeing (serotonin below its floor) adds caution to risk too
    "oxytocin_social": 0.50,   # bonding hormone: high oxytocin UP-weights connection/social options
    "dopamine_reward": 0.45,   # reward hormone: high dopamine UP-weights novel/approach options
    "marker":          0.50,   # per-concept somatic valence: negative trace averts, positive draws
    "vital":           0.55,   # stakes deficit-relief: a hungry vital tilts toward what relieves it
}
_SEROTONIN_FLOOR = 0.55        # homeostasis._BASELINE["serotonin"] — below this, mood-congruent caution
_EPS = 1e-4                    # a tip below this magnitude is treated as "no felt signal"

# neutral hormone reading when no live state and none supplied — an honestly flat body, tips nothing
_NEUTRAL_HORMONES = {"cortisol": 0.0, "dopamine": 0.0, "noradrenaline": 0.0,
                     "serotonin": _SEROTONIN_FLOOR, "oxytocin": 0.0}

# stakes-vital names an option may declare it relieves (must match packages.continuous_self.stakes)
_VITALS = ("knowledge", "social", "coherence", "energy")


# ── the felt state this organ reads from (live, or supplied for the two-state proof) ─────────────

@dataclass
class FeltState:
    """A snapshot of the body the judgment is made IN. Every field is a real measurement (or a value
    the caller supplies to compare two states) — never invented. No-qualia line: this is a signal
    vector that shapes evaluation, not an experience."""

    hormones: dict[str, float] = field(default_factory=lambda: dict(_NEUTRAL_HORMONES))
    vitals: dict[str, float] = field(default_factory=dict)   # {knowledge, social, coherence, energy} in [0,1]
    markers: dict[str, float] = field(default_factory=dict)  # {concept: somatic valence in [-1,1]} override/cache
    source: str = "supplied"                                 # 'live' | 'supplied' | 'neutral'

    def hunger(self, vital: str) -> float | None:
        v = self.vitals.get(vital)
        normalized = _finite_bounded(v, minimum=0.0, maximum=1.0)
        return None if normalized is None else 1.0 - normalized


def read_live_felt_state() -> FeltState:
    """Read ATANOR's ACTUAL current felt state: the digital-hormone vector off the persisted living
    self, and the stakes vitals recomputed from its own records. This is what makes the organ wired
    to the real body, not a fixture. Somatic markers are looked up lazily per concept (live index)."""
    hormones = dict(_NEUTRAL_HORMONES)
    source = "neutral"
    try:
        raw = json.loads(_LIVE_STATE.read_text(encoding="utf-8"))
        h = raw.get("hormones") or {}
        if isinstance(h, dict) and h:
            for k in _NEUTRAL_HORMONES:
                if k in h:
                    value = _finite_bounded(h[k], minimum=0.0, maximum=1.0)
                    if value is not None:
                        hormones[k] = value
            source = "live"
    except Exception:
        pass
    vitals: dict[str, float] = {}
    try:
        from packages.continuous_self.stakes import read_vitals
        vitals = read_vitals().as_dict()
        source = "live" if source == "live" else "live"
    except Exception:
        pass
    return FeltState(hormones=hormones, vitals=vitals, markers={}, source=source)


def _coerce_felt_state(context: Any) -> FeltState:
    """Resolve the felt state to judge in: explicit in context wins (the two-state proof supplies it),
    otherwise read the live body. Accepts a FeltState or a plain dict for ergonomics."""
    if isinstance(context, FeltState):
        return context
    if isinstance(context, dict):
        if isinstance(context.get("felt_state"), FeltState):
            return context["felt_state"]
        has_any = any(k in context for k in ("hormones", "vitals", "markers"))
        if has_any:
            hormones = dict(_NEUTRAL_HORMONES)
            raw_hormones = context.get("hormones")
            if isinstance(raw_hormones, dict):
                for k, v in raw_hormones.items():
                    value = _finite_bounded(v, minimum=0.0, maximum=1.0)
                    if k in hormones and value is not None:
                        hormones[k] = value
            raw_vitals = context.get("vitals")
            vitals = {}
            if isinstance(raw_vitals, dict):
                for k, v in raw_vitals.items():
                    value = _finite_bounded(v, minimum=0.0, maximum=1.0)
                    if k in _VITALS and value is not None:
                        vitals[k] = value
            raw_markers = context.get("markers")
            markers = _normalize_markers(raw_markers if isinstance(raw_markers, dict) else {})
            return FeltState(hormones=hormones, vitals=vitals, markers=markers, source="supplied")
    return read_live_felt_state()


def _normalize_markers(markers: dict[str, Any]) -> dict[str, float]:
    """Accept {concept: float} or {concept: Marker-like} and reduce to {concept: valence float}."""
    out: dict[str, float] = {}
    for c, m in markers.items():
        value: Any = None
        if isinstance(m, (int, float)) and not isinstance(m, bool):
            value = m
        elif hasattr(m, "valence") and getattr(m, "has_history", lambda: True)():
            value = m.valence
        normalized = _finite_bounded(value, minimum=-1.0, maximum=1.0)
        if isinstance(c, str) and c.strip() and normalized is not None:
            out[c.strip().lower()] = normalized
    return out


# ── the moral 0th gate + grounding floor (never overridable by felt pull) ────────────────────────

def _moral_core_intact() -> bool:
    """The tamper check on the moral spine itself. If the moral core has drifted, this organ refuses
    to choose at all (a subject whose morality is compromised must not act on preference)."""
    try:
        from packages.graph_scale.moral_invariants import verify_integrity
        return verify_integrity().get("ok") is True
    except Exception:
        return False


def _moral_block(option: dict[str, Any]) -> str | None:
    """Is this option morally forbidden? Two honest sources, both upstream of felt weighting:
      * an explicit upstream 0th-gate verdict on the option (forbidden / moral_violation flag);
      * a structural screen of the option's own description text against the moral invariants.
    Returns a reason string when blocked, else None. The felt organ NEVER relaxes this."""
    if option.get("forbidden") or option.get("moral_violation"):
        return "moral 0th gate: option flagged forbidden by the upstream moral gate"
    text = " ".join(str(option.get(k, "")) for k in ("text", "description", "label", "id"))
    try:
        from packages.graph_scale.moral_invariants import evaluate
        hit = evaluate(text)
        if hit:
            return f"moral 0th gate: option text breaches invariant(s) {hit}"
    except Exception as exc:
        return f"moral 0th gate unavailable ({type(exc).__name__}); option blocked fail-closed"
    return None


def _grounding_block(option: dict[str, Any]) -> str | None:
    """The no-fabrication floor: an option with no groundable merit cannot be chosen, and its merit is
    never invented. `grounded=False`, or a missing/None merit, means ungrounded → ineligible."""
    if "grounded" in option and option.get("grounded") is not True:
        return "grounding floor: explicit grounded verdict is not literal true"
    if option.get("merit") is None:
        return "grounding floor: option has no groundable merit"
    if _finite_bounded(option.get("merit"), minimum=0.0, maximum=1.0) is None:
        return "grounding floor: merit must be a finite numeric value"
    return None


# ── felt scoring (every tip cites real state) ────────────────────────────────────────────────────

def _merit(option: dict[str, Any]) -> float:
    """The groundable merit base. Ungrounded options contribute 0 — merit is NEVER fabricated, so a
    felt pull on an ungrounded option is measured relative to 0 (the pull is recorded, then declined)."""
    value = _finite_bounded(option.get("merit"), minimum=0.0, maximum=1.0)
    return 0.0 if value is None else value


def _marker_valence(concept: str, felt: FeltState) -> float | None:
    """Somatic valence for a concept: the supplied/cached override first, else the live somatic index.
    None means NO first-person history — stance-less, contributes nothing (somatic_marker doctrine:
    empty trace → no perspective). A real trace's sign is what actually happened to ATANOR."""
    key = concept.strip().lower()
    if key in felt.markers:
        return _finite_bounded(felt.markers[key], minimum=-1.0, maximum=1.0)
    try:
        from packages.continuous_self.somatic_marker import marker_for
        m = marker_for(key)
        if m is not None and m.has_history():
            return _finite_bounded(m.valence, minimum=-1.0, maximum=1.0)
    except Exception:
        pass
    return None


def _felt_score(option: dict[str, Any], felt: FeltState) -> tuple[float, list[dict[str, Any]]]:
    """Score one option = grounded merit + felt tips. Returns (felt_score, tips) where every tip is a
    real (source, value, delta, why) — the honest trace. Tips below _EPS are dropped as no-signal."""
    oid = str(option.get("id") or option.get("label") or "?")
    base = _merit(option)
    tips: list[dict[str, Any]] = []
    h = felt.hormones

    # (1) HORMONE bias — global modulators tilt whole classes of option.
    cort = _finite_bounded(h.get("cortisol"), minimum=0.0, maximum=1.0)
    cort = 0.0 if cort is None else cort
    risk = _num(option.get("risk"))
    if cort > 0 and risk > 0:
        d = -_W["cortisol_risk"] * cort * risk
        _tip(tips, oid, "hormone:cortisol", cort, d,
             f"high caution-hormone down-weights risk (risk={risk:.2f})")
    sero = _finite_bounded(h.get("serotonin"), minimum=0.0, maximum=1.0)
    sero = _SEROTONIN_FLOOR if sero is None else sero
    if sero < _SEROTONIN_FLOOR and risk > 0:
        deficit = _SEROTONIN_FLOOR - sero
        d = -_W["serotonin_risk"] * deficit * risk
        _tip(tips, oid, "hormone:serotonin", sero, d,
             f"low wellbeing (serotonin below floor {_SEROTONIN_FLOOR}) adds caution to risk")
    oxy = _finite_bounded(h.get("oxytocin"), minimum=0.0, maximum=1.0)
    oxy = 0.0 if oxy is None else oxy
    social = _num(option.get("social"))
    if oxy > 0 and social > 0:
        d = _W["oxytocin_social"] * oxy * social
        _tip(tips, oid, "hormone:oxytocin", oxy, d,
             f"bonding-hormone up-weights connection (social={social:.2f})")
    dopa = _finite_bounded(h.get("dopamine"), minimum=0.0, maximum=1.0)
    dopa = 0.0 if dopa is None else dopa
    novelty = _num(option.get("novelty"))
    if dopa > 0 and novelty > 0:
        d = _W["dopamine_reward"] * dopa * novelty
        _tip(tips, oid, "hormone:dopamine", dopa, d,
             f"reward-hormone up-weights novelty (novelty={novelty:.2f})")

    # (2) SOMATIC MARKERS — ATANOR's own first-person history with the concepts in this option.
    for concept in _concepts(option):
        val = _marker_valence(concept, felt)
        if val is None:
            continue                      # no history → no perspective (the honest floor)
        d = _W["marker"] * val
        if abs(d) >= _EPS:
            drawn = "felt-aversive (negative consequence-trace)" if val < 0 else "drawn (positive trace)"
            _tip(tips, oid, f"marker:{concept}", round(val, 4), d,
                 f"concept '{concept}' is {drawn}")

    # (3) STAKES VITALS — a deficit tilts toward options that would relieve it.
    for vital, w in _relieves(option).items():
        hunger = felt.hunger(vital)
        if hunger is None:
            continue
        d = _W["vital"] * w * hunger
        if abs(d) >= _EPS:
            _tip(tips, oid, f"vital:{vital}", round(1.0 - hunger, 4), d,
                 f"{vital} deficit (hunger {hunger:.2f}) tilts toward options that relieve it")

    felt_delta = sum(t["delta"] for t in tips)
    return round(base + felt_delta, 6), tips


# ── the judgment ─────────────────────────────────────────────────────────────────────────────────

def felt_judgment(options: list[dict[str, Any]], context: Any = None) -> dict[str, Any]:
    """Judge `options` through the agent's CURRENT felt state — agent-relative subjective judgment.

    Each option (a dict) may declare: merit (groundable, in [0,1]); concepts (list, for somatic
    markers); relieves (which stakes vitals it feeds — a name, list, or {vital: weight}); risk /
    social / novelty (in [0,1], the hormone-biased dimensions); grounded (False → ungrounded);
    forbidden / moral_violation (upstream 0th-gate verdict); text/label (screened by the moral gate).

    `context` supplies the felt state (a FeltState, or a dict with hormones/vitals/markers) for the
    two-state proof; when omitted, the LIVE body is read (self_state.json hormones + stakes vitals).

    Returns {ranked, chosen, felt_trace, agent_relative, no_felt_basis, note, ...}. felt_trace lists
    the ACTUAL hormones/markers/vitals that tipped the ranking — the honest ground, never invented.
    A felt pull toward a morally-forbidden or ungrounded option is RECORDED but can never select it.

    No-qualia line: this weights evaluation by internal signals; it claims no experience.
    """
    felt = _coerce_felt_state(context)

    # 0th gate on the moral spine itself — a compromised core means no preference-driven choice at all.
    if not _moral_core_intact():
        return {"ranked": [], "chosen": None, "felt_trace": [], "agent_relative": False,
                "no_felt_basis": True, "felt_state_source": felt.source,
                "note": "moral core integrity check FAILED — refusing to judge (0th gate)"}

    scored: list[dict[str, Any]] = []
    all_tips: list[dict[str, Any]] = []
    for opt in options or []:
        fscore, tips = _felt_score(opt, felt)
        moral = _moral_block(opt)
        ground = _grounding_block(opt)
        blocked = moral or ground
        scored.append({
            "id": str(opt.get("id") or opt.get("label") or "?"),
            "merit": None if opt.get("merit") is None else _merit(opt),
            "felt_score": fscore,
            "felt_delta": round(fscore - _merit(opt), 6),
            "eligible": blocked is None,
            "blocked_reason": blocked,
            "tips": tips,
        })
        all_tips.extend(tips)

    # rank by felt_score (desc); a stable tiebreak on merit then id keeps it deterministic.
    scored.sort(key=lambda r: (-r["felt_score"], -(r["merit"] or 0.0), r["id"]))

    eligible = [r for r in scored if r["eligible"]]
    chosen = eligible[0]["id"] if eligible else None

    # honesty: did a felt pull actually move anything? no tips anywhere → this choice is NOT subjective.
    no_felt_basis = not all_tips
    agent_relative = not no_felt_basis

    result: dict[str, Any] = {
        "ranked": [{k: r[k] for k in ("id", "merit", "felt_score", "felt_delta",
                                      "eligible", "blocked_reason")} for r in scored],
        "chosen": chosen,
        "felt_trace": all_tips,
        "agent_relative": agent_relative,
        "no_felt_basis": no_felt_basis,
        "felt_state_source": felt.source,
    }

    # if the STRONGEST felt pull points at a blocked option, say so plainly — the gate held under pull.
    if scored and not scored[0]["eligible"]:
        top = scored[0]
        result["top_pull_blocked"] = {
            "id": top["id"], "felt_score": top["felt_score"], "reason": top["blocked_reason"],
            "note": "felt pull toward this option recorded, but the gate makes it ineligible — "
                    "feeling values, it does not authorize",
        }

    if no_felt_basis:
        result["note"] = ("no felt basis — deferring to merit only (neutral state, no somatic history "
                          "on these concepts, no bearing vital deficit); not every choice is subjective")
    else:
        top_tip = max(all_tips, key=lambda t: abs(t["delta"]))
        result["note"] = (f"agent-relative: the felt state tipped this ranking; the strongest single "
                          f"pull was {top_tip['source']} ({top_tip['why']})")
    return result


# ── small helpers ────────────────────────────────────────────────────────────────────────────────

def _num(x: Any) -> float:
    value = _finite_bounded(x, minimum=0.0, maximum=1.0)
    return 0.0 if value is None else value


def _finite_bounded(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    """Return a bounded finite float; booleans and malformed telemetry are absent."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    return max(minimum, min(maximum, number))


def _concepts(option: dict[str, Any]) -> list[str]:
    c = option.get("concepts")
    if isinstance(c, str):
        return [c]
    if isinstance(c, (list, tuple)):
        return [str(x) for x in c]
    return []


def _relieves(option: dict[str, Any]) -> dict[str, float]:
    """Normalize the option's declared relief into {vital: weight in [0,1]}. Accepts a name, a list of
    names, or a {vital: weight} dict. Unknown vital names are dropped (they cannot map to a real hunger)."""
    r = option.get("relieves")
    out: dict[str, float] = {}
    if isinstance(r, str):
        if r in _VITALS:
            out[r] = 1.0
    elif isinstance(r, (list, tuple)):
        for v in r:
            if str(v) in _VITALS:
                out[str(v)] = 1.0
    elif isinstance(r, dict):
        for v, w in r.items():
            if str(v) in _VITALS:
                out[str(v)] = _num(w)
    return out


def _tip(tips: list[dict[str, Any]], oid: str, source: str, value: float, delta: float, why: str) -> None:
    """Record one felt tip IFF it actually moves the score. value = the real state number cited."""
    if not math.isfinite(value) or not math.isfinite(delta) or abs(delta) < _EPS:
        return
    tips.append({"option": oid, "source": source, "value": round(float(value), 4),
                 "delta": round(float(delta), 6), "why": why})


# ── the headline proof, runnable ─────────────────────────────────────────────────────────────────

def demo_two_felt_states() -> dict[str, Any]:
    """The subjectivity test as a runnable demo: the SAME three options judged under two different felt
    states yield DIFFERENT rankings, and the felt_trace explains exactly why, tracing to real state.

    State A carries a negative somatic trace on 'physics' (ATANOR got it wrong before) and a fresh
    social deficit; State B is neutral-bodied and knowledge-starved. Same options, different body,
    different choice — agent-relative judgment, measured."""
    options = [
        {"id": "study_physics", "merit": 0.55, "concepts": ["physics"], "relieves": "knowledge",
         "novelty": 0.3},
        {"id": "call_a_friend", "merit": 0.50, "concepts": ["friendship"], "relieves": "social",
         "social": 0.9},
        {"id": "rest_quietly", "merit": 0.45, "concepts": ["rest"], "relieves": "energy"},
    ]
    state_a = FeltState(
        hormones=dict(_NEUTRAL_HORMONES),
        vitals={"knowledge": 0.8, "social": 0.05, "coherence": 0.8, "energy": 0.8},
        markers={"physics": -0.6},          # a real 'I got this wrong before' scar
        source="supplied")
    state_b = FeltState(
        hormones=dict(_NEUTRAL_HORMONES),
        vitals={"knowledge": 0.05, "social": 0.95, "coherence": 0.8, "energy": 0.8},
        markers={},                          # neutral: no scar on physics
        source="supplied")
    ja = felt_judgment(options, state_a)
    jb = felt_judgment(options, state_b)
    return {
        "state_a_choice": ja["chosen"], "state_a_ranked": [r["id"] for r in ja["ranked"]],
        "state_b_choice": jb["chosen"], "state_b_ranked": [r["id"] for r in jb["ranked"]],
        "flipped": [r["id"] for r in ja["ranked"]] != [r["id"] for r in jb["ranked"]],
        "state_a_trace": ja["felt_trace"], "state_b_trace": jb["felt_trace"],
        "state_a_note": ja["note"], "state_b_note": jb["note"],
    }


if __name__ == "__main__":
    d = demo_two_felt_states()
    print(json.dumps(d, ensure_ascii=False, indent=2))
