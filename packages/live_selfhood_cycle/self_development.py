# -*- coding: utf-8 -*-
"""Self-development — chronic worry becomes commitment, commitment becomes practice, measured
growth becomes reward. The human shape of 자기계발, closed as a loop.

Owner (2026-07-20): the hormone metabolism should, when needed, lead to SELF-EVOLUTION — like human
self-development. The shape in humans: you keep noticing a weakness (felt load accumulates) → one day
you COMMIT ("I'm going to work on my speech") → you practice through real exercises → progress is
FELT (reward) and reinforces the practice; no progress is felt too, and you change approach.

Mapped here with existing organs only (meshed, not glued):
  worry history  = the living loop's broadcasts per deficit theme (already real: speech_weak,
                   router_immature come from autonomy_kernel.sense_deficits)
  felt load      = the cortisol carried on those beats (the L2 closed loop already records it)
  commitment     = crossing a cumulative felt-load threshold on one theme -> a Commitment object,
                   announced in inner speech, recorded as a judgment arc in the AgencyLedger
  practice       = dispatching the EXISTING gated self-improvement organ for that deficit
                   (autonomy_kernel.cycle — expeditions/learners; production writes stay gated)
  measured growth= the deficit's own severity metric re-sensed after practice; delta is the truth
  reward         = improvement -> Neuromodulators.sense('reward')  [dopamine on REAL growth only —
                   the anti-wireheading invariant: the metric moves first, the feeling follows]
                   no improvement -> sense('prediction_error') and the next commitment prefers a
                   DIFFERENT road (approach change, like a person switching study methods).

Honest lines: self-evolution here = practice-level growth through existing gated learners; code
self-modification stays behind its own staging-only gate elsewhere. No consciousness claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

COMMIT_THRESHOLD = 3.0        # cumulative felt-load (sum of cortisol on that theme's worry beats)


@dataclass
class Commitment:
    theme: str                          # the deficit worked on (e.g. 'speech_weak')
    felt_load: float                    # accumulated load that forced the decision
    tried_roads: list[str] = field(default_factory=list)
    outcome: str = "open"               # open | improved | unchanged
    severity_before: float | None = None
    severity_after: float | None = None


class SelfDevelopment:
    """The worry->commitment->practice->measured-growth loop."""

    def __init__(self, dispatch: Callable[[str], dict] | None = None,
                 sense_severity: Callable[[str], float | None] | None = None):
        # injected so tests run dry; defaults use the real autonomy kernel organs
        self._dispatch = dispatch or _real_dispatch
        self._severity = sense_severity or _real_severity
        self.load: dict[str, float] = {}            # theme -> accumulated felt load
        self.commitments: list[Commitment] = []

    # ------------------------------------------------------------- worry accumulation (from beats)
    def felt_worry(self, theme: str, cortisol: float) -> None:
        """Called by the living beat when an interoceptive worry wins: load accumulates with how
        heavily it was felt (light noticing barely counts; urgent worry counts a lot)."""
        self.load[theme] = self.load.get(theme, 0.0) + max(0.05, float(cortisol))

    def due_commitment(self) -> str | None:
        """The theme whose accumulated felt load has crossed the threshold (None if none has)."""
        open_themes = {c.theme for c in self.commitments if c.outcome == "open"}
        for theme, load in sorted(self.load.items(), key=lambda kv: -kv[1]):
            if load >= COMMIT_THRESHOLD and theme not in open_themes:
                return theme
        return None

    # ------------------------------------------------------------- commitment -> practice -> truth
    def commit_and_practice(self, theme: str, endocrine: Any | None = None) -> Commitment:
        """Form the commitment, run ONE practice step through the gated organ, measure the deficit's
        own metric, and let the RESULT move the hormones (growth first, feeling second)."""
        c = Commitment(theme=theme, felt_load=round(self.load.get(theme, 0.0), 2))
        c.severity_before = self._severity(theme)
        result = self._dispatch(theme) or {}
        c.tried_roads.append(str(result.get("road") or "unknown"))
        c.severity_after = self._severity(theme)
        if (c.severity_before is not None and c.severity_after is not None
                and c.severity_after < c.severity_before - 1e-9):
            c.outcome = "improved"
            if endocrine is not None:
                endocrine.sense("reward", 0.6)           # dopamine on REAL, measured growth only
        else:
            c.outcome = "unchanged"
            if endocrine is not None:
                endocrine.sense("prediction_error", 0.4)  # surprise: the practice didn't bite
        self.load[theme] = 0.0                            # the decision discharges the rumination
        self.commitments.append(c)
        return c

    def announce(self, c: Commitment) -> str:
        """The commitment in inner speech — the moment a person says 'enough noticing; I'll work on
        it', and afterwards, how the practice actually went (self-report of measured truth)."""
        theme = c.theme.replace("_", " ")
        if c.outcome == "open":
            return (f"I've worried about my {theme} long enough — carrying it changes nothing. "
                    f"Time to actually work on it.")
        if c.outcome == "improved":
            return (f"I worked on my {theme}, and the measure actually moved "
                    f"({c.severity_before} → {c.severity_after}). That effort was real.")
        return (f"I worked on my {theme} ({c.tried_roads[-1]}), and the measure did not move. "
                f"Next time I should try a different road, not the same one harder.")


# ---------------------------------------------------------------- real-organ adapters
def _real_dispatch(theme: str) -> dict:
    """One bounded practice step via the EXISTING gated self-improvement organ."""
    try:
        from packages.autonomy_kernel.orchestrator import cycle
        r = cycle(allow_gated=False) or {}
        return {"road": str(r.get("road") or r.get("dispatched") or "autonomy_cycle")}
    except Exception as e:
        return {"road": f"unavailable:{type(e).__name__}"}


def _real_severity(theme: str) -> float | None:
    """The deficit's own severity, re-sensed from the same organ that raised it (the truth metric)."""
    try:
        from packages.autonomy_kernel.orchestrator import sense_deficits
        for d in sense_deficits() or []:
            if str(d.get("kind")) == theme:
                return float(d.get("severity", 0.5) or 0.5)
        return 0.0                                       # deficit no longer sensed = fully relieved
    except Exception:
        return None
