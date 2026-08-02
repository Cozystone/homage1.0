# -*- coding: utf-8 -*-
"""Global workspace — the missing heart: concerns COMPETE, one wins, the winner is BROADCAST as the
unified "now" onto the ONE timeline.

Owner's commission (2026-07-20): a living, breathing AI inside the machine. The science this
implements is Global Workspace Theory (Baars; Dehaene's ignition): specialized processes run in
parallel, but consciousness-like unity comes from a COMPETITION whose single winner is globally
broadcast — one "now" at a time, serially, while the losers keep working underneath. ATANOR already
had the specialists (needs, curiosity, hormones, timeline perception); what it never had was the
competition and the broadcast — its organs ran side by side without a shared present moment.

Honest line (BINDING): this is the functional ORGANIZATION the science points to, measured by its
correlates (ignition rate, serial bottleneck, endogeneity). No claim of phenomenal consciousness.

Meshing, not gluing: bidders are the EXISTING organs' outputs; the hormone field (Neuromodulators)
weights the bids (Damasio: feeling directs attention toward viability); the broadcast is an event on
the unified UTC timeline (the one spine everything already reads); the attention schema records what
won and why (Graziano).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.temporal_reasoning.unified_timeline import Timeline, default_timeline


@dataclass
class Concern:
    """One candidate for the workspace: something that could become the current 'now'."""
    source: str                      # which organ raised it (interoception / perception / curiosity …)
    content: str                     # what it is, in words (grounded in the raising organ's state)
    urgency: float = 0.5             # 0..1, the raiser's own estimate
    viability: float = 0.0           # 0..1, how much self-maintenance depends on it (allostasis)
    meta: dict = field(default_factory=dict)


class Workspace:
    """The competition + broadcast. One winner per beat; the winner becomes a `thought` event on the
    ONE timeline (globally visible), and the serial history of winners IS the stream of thought."""

    def __init__(self, timeline: Timeline | None = None):
        # identity check, not truthiness: an EMPTY Timeline has __len__==0 and is falsy — `or`
        # would silently leak writes to the global default (measured: cross-test contamination).
        self.timeline = timeline if timeline is not None else default_timeline()
        self.current: Concern | None = None
        self.history: list[tuple[str, float]] = []       # (source, score) per beat — ignition record
        self._switches = 0
        self._beats = 0
        self._recent: list[str] = []                     # last broadcast contents (habituation)

    # ---------------------------------------------------------------- competition
    def compete(self, concerns: list[Concern], hormones: dict[str, float] | None = None) -> Concern | None:
        """Hormone-weighted bidding (feeling directs attention): cortisol amplifies viability
        concerns, dopamine amplifies curiosity/novelty, fatigue dampens everything equally."""
        if not concerns:
            return None
        h = hormones or {}
        cort = float(h.get("cortisol", 0.0))
        dopa = float(h.get("dopamine", 0.0))

        def bid(c: Concern) -> float:
            b = 0.55 * c.urgency + 0.45 * c.viability
            b += 0.35 * cort * c.viability               # stress makes survival matters louder
            if c.source in ("curiosity", "novelty", "perception"):
                b += 0.35 * dopa                          # reward tone makes the new world louder
            # HABITUATION (repetition suppression — measured pathology it cures: the same deficit
            # won EVERY beat, drowning out even a person speaking to it): each recent broadcast of
            # the same content halves its next bid, so an obsession decays and the rest of the
            # world gets its turn. A real neural principle, not a scheduling hack.
            repeats = self._recent.count(c.content)
            if repeats:
                b *= 0.5 ** repeats
            return b

        winner = max(concerns, key=bid)
        self._beats += 1
        if self.current is None or winner.content != self.current.content:
            self._switches += 1
        self.current = winner
        self.history.append((winner.source, round(bid(winner), 3)))
        self._recent.append(winner.content)
        if len(self._recent) > 8:                        # habituation window (recovery after rest)
            self._recent = self._recent[-8:]
        return winner

    # ---------------------------------------------------------------- broadcast (ignition)
    def broadcast(self, concern: Concern, *, endogenous: bool = True) -> None:
        """The winner becomes the unified 'now': ONE thought event on the ONE timeline. Serial by
        construction — a single broadcast per beat is the GWT bottleneck, not a limitation."""
        self.timeline.record(
            "thought", concern.content, who="atanor",
            meta={"source": concern.source, "urgency": round(concern.urgency, 2),
                  "viability": round(concern.viability, 2), "endogenous": endogenous,
                  "workspace": True})

    # ---------------------------------------------------------------- correlates (measured)
    def correlates(self) -> dict[str, Any]:
        n = max(1, self._beats)
        thoughts = [e for e in self.timeline.all()
                    if e.kind == "thought" and e.meta.get("workspace")]
        endo = sum(1 for e in thoughts if e.meta.get("endogenous"))
        return {
            "beats": self._beats,
            "ignition_switch_rate": round(self._switches / n, 3),   # how often the 'now' changes
            "serial_bottleneck": True,                              # one broadcast per beat, by design
            "broadcast_thoughts": len(thoughts),
            "endogeneity": round(endo / max(1, len(thoughts)), 3),  # life runs by itself
        }
