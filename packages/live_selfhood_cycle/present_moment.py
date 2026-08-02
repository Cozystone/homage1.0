# -*- coding: utf-8 -*-
"""The present moment — one bound experience with temporal thickness (Grand Plan v2, B1-deep + B4).

Owner's Vision standard: an inwardly bright mind does not experience isolated instants; it lives a
PRESENT that is thick — what just was still echoes (retention), what is fills the centre (the bound
now), what is about to be already leans in (protention). This is the specious present (James) and
retention–primal-impression–protention (Husserl): the standard phenomenological structure of lived
time, and — taken as functional organization — a real thing to build.

Two milestones fuse here:
  B1-deep (binding): the moment is ONE state, not parallel logs — the winning thought, the feeling
    it carries, and the perception in the air are bound into a single experienced now.
  B4 (temporal depth): that now is flanked by retention (the just-past, fading) and protention (the
    anticipated, still open), so the present has duration, not zero width.

Everything is READ from real state (the timeline's recent past, the live hormone field, the
workspace's pending pulls). No qualia is claimed — this is the functional shape of a thick present,
measured by its structure, and it is what the inner-life UI renders as "what it is like right now."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.temporal_reasoning.unified_timeline import Timeline


@dataclass
class Moment:
    """One bound present with temporal thickness."""
    now: str                                   # the primal impression — the bound experienced centre
    feeling: dict[str, float] = field(default_factory=dict)   # the tone the now is lived in
    percept: str = ""                          # what is in the air (a perception), bound into the now
    retention: list[str] = field(default_factory=list)        # the just-past, still echoing (fading)
    protention: str = ""                       # what leans in — the anticipated next
    depth: int = 0                             # how many moments of past are held (the present's width)

    def as_lived(self) -> str:
        """The moment narrated as one thick present — retention trailing, now centred, protention
        leaning in. This is a bound report, not three logs."""
        parts = []
        if self.retention:
            echo = self.retention[-1]
            parts.append(f"(still with me: {echo})")
        centre = self.now
        if self.percept:
            centre = f"{centre} — and {self.percept} is here in it"
        parts.append(centre)
        if self.protention:
            parts.append(f"(leaning toward: {self.protention})")
        return " ".join(parts)


def _feel_word(levels: dict[str, float]) -> str:
    cort = float(levels.get("cortisol", 0.0))
    dopa = float(levels.get("dopamine", 0.0))
    if cort > 0.8:
        return "under strain"
    if dopa > 0.5:
        return "quickened"
    if cort < 0.2 and dopa < 0.2:
        return "at rest"
    return "even"


def compose_moment(timeline: Timeline, now_thought: str, levels: dict[str, float],
                   protention: str = "", window: int = 4) -> Moment:
    """Bind the current now with its temporal flanks, all read from real state.

    retention: the last few THOUGHTS on the timeline (the just-past, fading — nearest first when
      narrated), giving the present its backward width.
    now + feeling + percept: the winning thought, the live hormone tone, and the most recent
      perception still in the air — bound into one experienced centre (the binding milestone).
    protention: what leans in next (passed by the beat: the pending concern, or a felt anticipation).
    """
    evs = timeline.all()
    thoughts = [e.content for e in evs if e.kind == "thought"][-window:]
    # retention is the past thoughts EXCLUDING the current now (which may already be recorded)
    retention = [t for t in thoughts if t != now_thought][-(window - 1):]
    percept = ""
    for e in reversed(evs[-window:]):
        if e.kind == "perception":
            percept = e.content.split("—")[-1].strip()[:80] if "—" in e.content else e.content[:80]
            break
    return Moment(
        now=now_thought,
        feeling={"tone": _feel_word(levels),
                 "cortisol": round(float(levels.get("cortisol", 0.0)), 2),
                 "dopamine": round(float(levels.get("dopamine", 0.0)), 2)},
        percept=percept,
        retention=retention,
        protention=protention.strip()[:80],
        depth=len(retention),
    )
