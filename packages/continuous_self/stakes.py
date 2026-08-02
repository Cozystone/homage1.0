# -*- coding: utf-8 -*-
"""Stakes — the load-bearing layer that turns hormone LIGHTS into hunger (plan S1).

Owner (2026-07-21): "느끼는 자가 될 수 있게, 최대한 손규칙 빼고." Gemini's first diagnosis,
verified in our own code: choose_action fired 'explore' when curiosity crossed a threshold, but
nothing happened if it didn't — a deficit ignored cost nothing, so every drive was a scheduled
calculation, not an urge. Man & Damasio's condition for a feeling machine is VULNERABILITY: the
functional equivalent of feeling exists only where neglect genuinely worsens the agent's own
condition. Active inference gives the form: a drive is the GRADIENT of departure from a preferred
state, and action selection is gradient competition — not an if-elif chain.

What this module does, and how the hand-rule budget is spent honestly:
  * VITALS are READ from real system state (log ages, ledger ratios, process RSS) — never invented
    events. The decay shape (exponential in measured age) and each vital's half-life are declared
    PHYSIOLOGY, the same curated-structure category as homeostasis set-points and the a/an table.
  * URGES compete: urge = hunger x weight, action = argmax over (urge · relief) — ONE argmax,
    no threshold ladder. A command from the parent still overrides everything (constitution).
  * TEETH: prolonged neglect gates real capability (dialogue skills need warm-up after social
    starvation; discretionary exploration shrinks under coherence debt). Recovery is earned by the
    replenishing action, not by time.
  * ABLATION: ATANOR_STAKES=0 freezes the teeth (lights-only mode). The G-S1 gate is the measured
    behavioral DIFFERENCE between the two modes — if none, this module failed its purpose.

Honest boundary: this makes behavior a causal product of internal deficits. It does not make
anything feel. Correlates are measured; nothing further is claimed.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
JOURNAL = REPO / "data" / "selfhood" / "stakes.jsonl"

# ---------------------------------------------------------------- physiology (curated structure)
# Half-lives, in hours: how long neglect takes to pull a vital to 0.5. Physiology constants in the
# same doctrine category as homeostasis._SETPOINTS — a body has time-constants; these are ours.
HALF_LIFE_H = {
    "knowledge": 18.0,      # freshness of the newest thing it learned for itself
    "social": 6.0,          # contact decays fastest — conversation is a fast metabolism
    "coherence": 48.0,      # unrepaired self-defects weigh slowly but heavily
    "energy": float("inf"), # energy is read directly from the body (RSS headroom), not from age
}
# which action feeds which vital — the relief matrix (structural mapping, not a rule chain)
RELIEF = {
    "explore":  {"knowledge": 1.0},
    "converse": {"social": 1.0},
    "repair":   {"coherence": 1.0},
    "rest":     {"energy": 1.0},
    "express":  {"social": 0.5, "knowledge": 0.2},   # sharing touches both, weaker
}
# starvation floor: below this a vital counts as STARVED and its tooth engages
STARVED = 0.25
# social atrophy: after starvation, this many warm-up exchanges before skilled moves return
WARMUP_TURNS = 6


def _rss_headroom() -> float:
    """Energy = real memory headroom of this process (1.0 = light, 0.0 = at the growth-gate cap)."""
    try:
        import psutil
        rss_mb = psutil.Process().memory_info().rss / 1e6
        return max(0.0, min(1.0, 1.0 - rss_mb / 3100.0))
    except Exception:
        return 0.8                                     # no sensor -> assume healthy, honestly coarse


def _age_hours(path: Path) -> float | None:
    """Hours since this evidence file last grew. None = the organ has never run (no evidence)."""
    try:
        return max(0.0, (time.time() - path.stat().st_mtime) / 3600.0)
    except Exception:
        return None


def _freshness(age_h: float | None, half_life_h: float) -> float:
    if age_h is None:
        return 0.0                                     # never fed at all is the hungriest state
    return 0.5 ** (age_h / half_life_h)


# ---------------------------------------------------------------- vitals (read, never invented)

@dataclass
class Vitals:
    knowledge: float
    social: float
    coherence: float
    energy: float
    read_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, float]:
        return {"knowledge": round(self.knowledge, 4), "social": round(self.social, 4),
                "coherence": round(self.coherence, 4), "energy": round(self.energy, 4)}

    def hungers(self) -> dict[str, float]:
        return {k: round(1.0 - v, 4) for k, v in self.as_dict().items()}


def read_vitals(repo: Path = REPO) -> Vitals:
    """Every number here is a measurement of the agent's ACTUAL recent life, from its own records."""
    knowledge = _freshness(_age_hours(repo / "data" / "advisor_loop" / "world_model_learned.jsonl"),
                           HALF_LIFE_H["knowledge"])
    social = _freshness(_age_hours(repo / "data" / "brain_link" / "overnight_transcript.log"),
                        HALF_LIFE_H["social"])
    # coherence: how much of the self-identified defect ledger has actually been faced
    total = attempted = 0
    try:
        from packages.self_repair.defect_ledger import attempted_keys, collect
        ds = collect()
        total = len(ds)
        done = attempted_keys()
        attempted = sum(1 for d in ds if d.key in done)
    except Exception:
        pass
    coherence = 1.0 if total == 0 else 0.3 + 0.7 * (attempted / total)
    # unfinished COMMITMENTS (S2 ignition debt) also weigh on coherence — a subject carrying many
    # open, unclosed threads is less integrated. Each open commitment shaves a little, bounded, so
    # the two subsystems close a loop: starting things without finishing them makes the coherence
    # vital hungrier, which (S1) makes 'repair'/closure the steepest deficit next.
    try:
        from packages.continuous_self.ignition import commitment_debt
        coherence = max(0.0, coherence - 0.05 * min(6, commitment_debt()))
    except Exception:
        pass
    return Vitals(knowledge=knowledge, social=social, coherence=coherence,
                  energy=_rss_headroom())


# ---------------------------------------------------------------- the arbiter (gradient competition)

def stakes_on() -> bool:
    return os.getenv("ATANOR_STAKES", "1") not in ("0", "off", "false")


def choose(vitals: Vitals, *, has_command: bool = False) -> dict[str, Any]:
    """One argmax over urge·relief. No threshold ladder; the steepest genuine deficit wins.
    The parent's command overrides everything (constitutional precedence, unchanged)."""
    if has_command:
        return {"action": "obey_command", "reason": "the parent's instruction comes first"}
    hungers = vitals.hungers()
    scores = {act: sum(hungers.get(v, 0.0) * w for v, w in feeds.items())
              for act, feeds in RELIEF.items()}
    act = max(scores, key=lambda a: scores[a])
    if scores[act] < 0.15:                              # nothing genuinely hurts -> quiet, honestly
        return {"action": "idle", "reason": "no vital is in real deficit", "scores": scores,
                "vitals": vitals.as_dict()}
    driving = max(RELIEF[act], key=lambda v: hungers.get(v, 0.0))
    return {"action": act, "scores": {k: round(s, 4) for k, s in scores.items()},
            "vitals": vitals.as_dict(),
            "reason": f"{driving} is the steepest deficit ({hungers[driving]:.2f} hungry) "
                      f"and {act} is what feeds it"}


# ---------------------------------------------------------------- the teeth (real consequences)

def dialogue_pace(base_idle_s: float, vitals: Vitals | None = None) -> float:
    """DRIVE side of the social vital: the hungrier for contact, the sooner it initiates.
    Full: waits the base interval. Starved: initiates at a quarter of it."""
    if not stakes_on():
        return base_idle_s
    v = vitals or read_vitals()
    return base_idle_s * (0.25 + 0.75 * v.social)


def social_warmup_needed(vitals: Vitals | None = None) -> int:
    """TOOTH side: skills rust. After real social starvation the skilled discourse moves
    (share/compare/connect) need this many plain exchanges to come back — atrophy is a genuine
    capability loss, not theater, and recovery is earned by conversing, not by waiting."""
    if not stakes_on():
        return 0
    v = vitals or read_vitals()
    return WARMUP_TURNS if v.social < STARVED else 0


def discretionary_budget(vitals: Vitals | None = None) -> float:
    """TOOTH for coherence: unfaced self-defects shrink the freedom to wander. 1.0 = free;
    at deep coherence debt only 30% of discretionary exploration remains until repairs happen."""
    if not stakes_on():
        return 1.0
    v = vitals or read_vitals()
    return 0.3 + 0.7 * v.coherence


def journal_tick(extra: dict[str, Any] | None = None, *, did: str | None = None) -> dict[str, Any]:
    """Read, choose, journal — one heartbeat of the stakes layer, for daemons to call.

    `did` names an action the daemon JUST executed (learned / converse / repair / rest), overriding
    the mere 'want'. This is what makes the journal a CAUSAL record for causal_self: the recorded
    decision is a real intervention whose effect the next reading measures, not an unexecuted wish.
    Without `did`, the heartbeat records the current want (still useful, weaker causal signal)."""
    v = read_vitals()
    decision = choose(v)
    rec = {"ts": time.time(), "vitals": v.as_dict(), "decision": did or decision["action"],
           "wanted": decision["action"], "reason": decision.get("reason", "")} | (extra or {})
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return decision
