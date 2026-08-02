# -*- coding: utf-8 -*-
"""Causal self-model — the laws ATANOR has LEARNED by living, mined from its own consequence.

Measured gap (2026-07-21): the graph is 83.6% is_a + alias and 0.35% causal — a dictionary, not a
model of how things work. GPT-5.4's peer verdict and the world-mentor's curriculum converge on the
same missing thing: "thick, persistent world-grounded context that lets meaning, relevance, and
consequence accumulate across time." Causal structure is that axis, and the honest, No-LLM way to
get it is not to inject asserted causes but to MINE them from consequence ATANOR actually underwent.

ATANOR has been living — daemons running, learning, repairing, leaving commitments open — and every
heartbeat wrote a real event journal. Those journals contain genuine causal structure the agent
OBSERVED about its own world: choose 'explore' while knowledge is hungry, and the knowledge vital
rises next reading; leave commitments open, and coherence falls. This module reads consecutive
journal states as (context, action) -> (outcome) transitions and induces regularities with SUPPORT
and CONFIDENCE counts — association over lived events, not a phrasing table, not a generator.

What it earns the right to say: predict("if I explore") -> the outcomes it has actually seen
follow; explain(a vital that changed) -> the actions that reliably precede it; and — the point —
speak a causal law ("exploring restores my knowledge") ONLY when its own history supports it, and
ABSTAIN otherwise. The no-fabrication floor, applied to causation: a cause claimed is a cause
observed, N times, in the agent's own record. As it lives longer, the model thickens — which is
exactly consequence accumulating across time.

Honest boundary: these are the agent's own action->effect regularities, correlational-with-
intervention-structure (the agent DID the action, so it is closer to causal than mere correlation,
but confounds are possible). Support counts are reported so nothing is oversold.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STAKES = REPO / "data" / "selfhood" / "stakes.jsonl"

# a vital counts as MOVED when it changes by at least this between consecutive readings
DELTA = 0.03
# a law needs at least this many supporting observations before it may be spoken
MIN_SUPPORT = 3
# and this much confidence (fraction of times the action was followed by the effect)
MIN_CONF = 0.6


@dataclass
class CausalLaw:
    action: str            # what the agent did
    vital: str             # which vital moved
    direction: str         # "rose" | "fell"
    support: int           # how many times this action+direction co-occurred
    trials: int            # how many times the action was taken at all
    confidence: float      # support / trials

    def speak(self) -> str:
        verb = {"rose": "restores", "fell": "depletes"}[self.direction]
        return (f"I have learned that {self.action} {verb} my {self.vital} "
                f"(observed {self.support} of {self.trials} times).")

    def record(self) -> dict:
        return {"action": self.action, "vital": self.vital, "direction": self.direction,
                "support": self.support, "trials": self.trials,
                "confidence": round(self.confidence, 3)}


def _transitions(path: Path | None = None) -> list[tuple[dict, str, dict]]:
    """Consecutive (vitals_before, decision, vitals_after) triples from the real stakes journal.
    Each heartbeat recorded the vitals it read and the action it chose; the NEXT heartbeat's vitals
    are the outcome of having taken that action. That sequence is a lived causal record."""
    path = path or STAKES
    rows = []
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r.get("vitals"), dict) and r.get("decision"):
            rows.append(r)
    out = []
    for a, b in zip(rows, rows[1:]):
        out.append((a["vitals"], a["decision"], b["vitals"]))
    return out


def induce_laws(path: Path | None = None) -> list[CausalLaw]:
    """Induce action -> vital-movement laws from lived transitions, with honest support counts."""
    path = path or STAKES
    trials: dict[str, int] = defaultdict(int)
    moved: dict[tuple[str, str, str], int] = defaultdict(int)
    for before, action, after in _transitions(path):
        trials[action] += 1
        for v in ("knowledge", "social", "coherence", "energy"):
            if v not in before or v not in after:
                continue
            d = after[v] - before[v]
            if d >= DELTA:
                moved[(action, v, "rose")] += 1
            elif d <= -DELTA:
                moved[(action, v, "fell")] += 1
    laws = []
    for (action, vital, direction), support in moved.items():
        t = trials[action]
        conf = support / t if t else 0.0
        if support >= MIN_SUPPORT and conf >= MIN_CONF:
            laws.append(CausalLaw(action, vital, direction, support, t, conf))
    laws.sort(key=lambda l: (-l.support, -l.confidence))
    return laws


# module cache — laws change only as the journal grows
_CACHE: list[CausalLaw] | None = None
_CACHE_N: int = -1


def laws(path: Path | None = None) -> list[CausalLaw]:
    global _CACHE, _CACHE_N
    path = path or STAKES
    n = path.stat().st_size if path.exists() else 0
    if _CACHE is None or n != _CACHE_N:
        _CACHE = induce_laws(path)
        _CACHE_N = n
    return _CACHE


def predict(action: str) -> list[CausalLaw]:
    """What has actually followed when the agent took this action? Empty = no lived evidence."""
    a = action.strip().lower()
    return [l for l in laws() if l.action.lower() == a]


def explain(vital: str, direction: str = "fell") -> list[CausalLaw]:
    """Which of the agent's own actions reliably precede this vital moving that way? The honest
    answer to 'why did my coherence fall' — from observation, not assertion."""
    v = vital.strip().lower()
    return [l for l in laws() if l.vital.lower() == v and l.direction == direction]


def speak_known_causes(limit: int = 3) -> list[str]:
    """The causal laws the agent has EARNED the right to state — or an empty list if it has not yet
    lived enough to know any. Abstention is the honest default; a young mind knows few laws."""
    return [l.speak() for l in laws()[:limit]]


def held_causal_laws(path: Path | None = None) -> list:
    """The causal laws ATANOR actually HOLDS — the strict lived inducer here plus the corroboration-
    promoted laws from causal_fuel (lived-directional + independently-attested wild-web candidates).
    Imported lazily to avoid an import cycle (causal_fuel reads _transitions from this module)."""
    from . import causal_fuel
    return causal_fuel.promoted_laws(path)


def speak_held_laws(limit: int = 5, path: Path | None = None) -> list[str]:
    """Speak the held (promoted) causal laws — or honest silence if none have been earned yet."""
    from . import causal_fuel
    return causal_fuel.speak_promoted(limit, path)


def coverage() -> dict[str, Any]:
    """How thick is the lived causal model right now — the 'accumulate across time' meter.

    ``laws_known`` is the count of causal laws ATANOR HOLDS: laws promoted by the corroboration
    counter (causal_fuel) from >= MIN_SUPPORT independent observations — lived transitions and/or
    distinct wild-web domains — never a fabricated bridge. It supersedes the earlier strict-lived-only
    count (still reported as ``laws_lived_strict``), which starved to 0 because it divided support by
    all trials. The HOT-3 belief-formation loop reads ``laws_known``; a held law is a formed belief.
    """
    ts = _transitions()
    strict = laws()
    try:
        from . import causal_fuel
        report = causal_fuel.fuel_report()
        promoted = int(report["promoted"])
        extra = {
            "laws_lived_strict": len(strict),
            "laws_promoted": promoted,
            "promoted_from_lived": int(report["promoted_from_lived"]),
            "promoted_corroborated": int(report["promoted_corroborated"]),
            "promoted_from_wildweb": int(report["promoted_from_wildweb"]),
            "hypotheses_pending": int(report["hypotheses_pending"]),
        }
        laws_known = promoted
    except Exception:
        # if the intake cannot run, fall back to the strict lived count — never crash the audit
        laws_known = len(strict)
        extra = {"laws_lived_strict": len(strict)}
    return {"transitions_observed": len(ts), "laws_known": laws_known,
            "min_support": MIN_SUPPORT, "min_confidence": MIN_CONF, **extra}
