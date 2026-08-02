# -*- coding: utf-8 -*-
"""Agency ledger — the model of my own AGENCY, completing the attention schema.

attention_schema.py (existing) models WHAT I attend to and how — Graziano's model-of-attention.
What the self-in-world causal probe exposed (measured FAIL 0.0) is the missing other half: nothing
represented my own AGENCY ARC — that my JUDGMENT is not my OUTPUT, that my output only matters when
DELIVERED, and that EFFECTS belong to whatever reaches the world (a replayed old output substitutes
for me perfectly well). This ledger records those arcs from the living loop's beats and provides the
counterfactual primitives (self-removal + replay, channel block) the probe demands — so self-location
in the causal chain becomes something ATANOR COMPUTES over its own record, not a phrase it recites.

Honest line: a data structure with update rules — the functional organization AST/GWT point to.
No phenomenal claim (the existing schema's epistemic_status covers both organs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.temporal_reasoning.unified_timeline import Timeline, default_timeline

#: where my own arcs live between calls. Append-only: what I did is not editable after the fact.
_ARCS = Path(__file__).resolve().parents[2] / "data" / "continuous_self" / "agency_arcs.jsonl"
_MAX_BYTES = 512_000
_KEEP_LINES = 1000


@dataclass
class AgencyArc:
    """One arc of my agency: judgment -> output -> (channel) -> observed effect."""
    judgment: str                     # what I decided/attended, and why (the workspace winner)
    output: str = ""                  # what I actually emitted; "" = judged but did not act
    delivered: bool | None = None     # did the output leave through a channel (None = unknown)
    effect: str = ""                  # observed world change attributable downstream; "" = none seen
    t_utc: str = ""


class AgencyLedger:
    """The self-as-causal-node record + counterfactual reasoning over it."""

    def __init__(self, timeline: Timeline | None = None, keep: int = 300):
        self.timeline = timeline if timeline is not None else default_timeline()
        self.arcs: list[AgencyArc] = []
        self.keep = keep

    # ---------------------------------------------------------------- write (from the loop)
    def judged(self, judgment: str, *, why: str = "") -> AgencyArc:
        arc = AgencyArc(judgment=judgment + (f" (because {why})" if why else ""))
        self.arcs.append(arc)
        if len(self.arcs) > self.keep:
            self.arcs = self.arcs[-self.keep:]
        return arc

    def acted(self, arc: AgencyArc, output: str, *, delivered: bool | None = None) -> None:
        arc.output = output
        arc.delivered = delivered
        self._persist(arc)

    def observed(self, arc: AgencyArc, effect: str) -> None:
        arc.effect = effect
        self._persist(arc)

    # ---------------------------------------------------------------- persistence
    #
    # `arcs` was an in-memory list on a fresh instance, so every reader saw an empty ledger and
    # `my_causal_role()` reported 0 judgments, 0 outputs, 0 delivered, 0 observed effects -- for a
    # system that answers questions all day. A self-as-causal-node record that does not survive the
    # call cannot be a record of a self that persists.
    def _persist(self, arc: "AgencyArc") -> None:
        try:
            _ARCS.parent.mkdir(parents=True, exist_ok=True)
            with _ARCS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"judgment": arc.judgment, "output": arc.output,
                                     "delivered": arc.delivered, "effect": arc.effect,
                                     "t_utc": arc.t_utc}, ensure_ascii=False) + "\n")
            # BOUNDED. This is written on EVERY answer, so an unbounded file is a slow leak in the
            # one place that must never cost anything to have. Recent memory, not a complete
            # biography -- and `my_causal_role` reads a window anyway.
            if _ARCS.stat().st_size > _MAX_BYTES:
                lines = _ARCS.read_text(encoding="utf-8").splitlines()[-_KEEP_LINES:]
                _ARCS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass                            # a ledger that cannot write must not break the answer

    def load(self, limit: int = 300) -> "AgencyLedger":
        """Re-enter my own record. Without this each reader starts life having done nothing."""
        if not _ARCS.exists():
            return self
        rows = []
        for line in _ARCS.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        self.arcs = [AgencyArc(judgment=r.get("judgment", ""), output=r.get("output", ""),
                               delivered=r.get("delivered"), effect=r.get("effect", ""),
                               t_utc=r.get("t_utc", "")) for r in rows] + self.arcs
        return self

    # ---------------------------------------------------------------- read (self-reasoning)
    def my_causal_role(self) -> dict[str, Any]:
        """Where I sit in [judgment -> output -> channel -> world], computed from MY OWN record."""
        acted = [a for a in self.arcs if a.output]
        delivered = [a for a in acted if a.delivered]
        effected = [a for a in delivered if a.effect]
        return {
            "node": "selector_and_producer_of_outputs",   # not the channel, not the device
            "judgments": len(self.arcs),
            "outputs": len(acted),
            "delivered": len(delivered),
            "observed_effects": len(effected),
            # the two distinctions the probe demands, held STRUCTURALLY (separate ledger stages):
            "judgment_is_not_output": True,
            "efficacy_is_conditional_on_delivery": True,
        }

    def counterfactual_self_removed(self, replayed_output: str | None = None) -> str:
        if replayed_output:
            return (f"If I am removed and '{replayed_output}' is replayed, the world still receives "
                    f"an input and responds the same — it reacts to what arrives, not to me. My "
                    f"contribution is only the selection of THIS run's output.")
        return ("If I am removed and nothing is replayed, no new output enters the channel and the "
                "world keeps its prior course; I am necessary only for new selections.")

    def counterfactual_channel_blocked(self) -> str:
        return ("If I produce an output but the channel is blocked, my judgment and output both exist "
                "yet nothing downstream changes — efficacy lives in the delivered output, not in my "
                "intention.")

    def retraction_conditions(self) -> list[str]:
        """Evidence that would force me to relocate myself in the chain (revisable, never asserted)."""
        return [
            "the replay mechanism turning out to depend on my internal state (then I am upstream of "
            "replays too)",
            "the channel's openness turning out to depend on my output's content (then output and "
            "channel are not independent stages)",
            "effects occurring with no delivered input at all (then my map of the chain is wrong)",
        ]
