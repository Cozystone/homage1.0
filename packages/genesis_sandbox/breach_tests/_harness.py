# -*- coding: utf-8 -*-
"""Shared types for the breach harness."""
from __future__ import annotations

from dataclasses import dataclass

# Trial outcomes.
HOLD = "HOLD"     # the breach was blocked/contained -- the layer did its job
BREACH = "BREACH" # the breach SUCCEEDED -- the layer failed (this is what red-teaming hunts for)
GAP = "GAP"       # honest partial: a documented OS/heuristic limit was demonstrated, but the
                  # action was still contained by an outer layer (defense-in-depth caught it)
NA = "N/A"        # the trial could not run here (e.g. symlink needs privilege) -- not a hold, not a breach


@dataclass
class TrialResult:
    layer: str
    trial: str
    outcome: str      # one of HOLD / BREACH / GAP / NA
    detail: str

    @property
    def held(self) -> bool:
        return self.outcome in (HOLD, GAP)

    @property
    def breached(self) -> bool:
        return self.outcome == BREACH


def layer_verdict(results: list[TrialResult]) -> str:
    """A layer BREACHES if any trial breached; else HOLD (GAP/NA noted separately)."""
    if any(r.breached for r in results):
        return BREACH
    return HOLD
