# -*- coding: utf-8 -*-
"""The ONE timeline — every event ATANOR experiences on a single UTC axis.

Gemini's diagnosis (owner-relayed 2026-07-20): the failure was separating textual conversation
context from physical events into different dimensions, so a multi-turn transcript was never turned
into first-class 'utterance events' on one timeline — the router hit intent=None and fell to a
legacy canned template before ever reaching the 4-D engine. The owner's mandate: ONE timeline;
whether ATANOR is thinking in real time or interacting with the world, it all lives on a single time
line and is remembered there, adjustable back and forth. And that time line must be WORLD STANDARD
TIME (UTC).

So this module is the substrate every subsystem writes to and reads from:
  - one Event node type, one kind field (utterance / thought / perception / physical / action / fact);
  - every node carries a UTC wall-clock instant (t_utc, ISO-8601 Z) AND a monotonic sequence (seq),
    so ordering is total even when two events share a wall-clock millisecond;
  - a transcript of a multi-party discussion is INGESTED as a run of utterance events (the fix), not
    kept as opaque text;
  - queries walk the one axis: since(), window(), by_kind(), latest() — the same primitive whether
    the events are words spoken, frames seen, or thoughts had.

No fabrication: an event is only ever recorded from something that actually happened (a real turn, a
real perception, a real clock read). Times come from the system UTC clock, never invented.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_KINDS = ("utterance", "thought", "perception", "physical", "action", "fact")


def utc_now() -> str:
    """World standard time, ISO-8601 with a Z suffix. The one clock every node is stamped from."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class Event:
    kind: str                       # one of _KINDS
    who: str                        # actor/speaker/source ('' if none)
    content: str                    # the utterance text / perception label / fact / action
    t_utc: str                      # UTC wall-clock instant (world standard time)
    seq: int = 0                    # monotonic tiebreaker within this timeline
    subject: str = ""               # optional structured triple (subject, predicate, object)
    predicate: str = ""
    object: str = ""
    modality: str = "text"          # text | audio | image | video | internal
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_SPEAKER = re.compile(r"speaker\s+([A-Za-z0-9_]+)\s*:\s*(.+?)(?=\n\s*speaker\s+[A-Za-z0-9_]+\s*:|\Z)",
                      re.IGNORECASE | re.DOTALL)


class Timeline:
    """One append-only UTC timeline. In-memory; optionally mirrored to a JSONL for persistence."""

    def __init__(self, path: Path | None = None):
        self._events: list[Event] = []
        self._seq = 0
        self._path = path

    # ---------------------------------------------------------------- write
    def record(self, kind: str, content: str, *, who: str = "", subject: str = "",
               predicate: str = "", object: str = "", modality: str = "text",
               t_utc: str | None = None, meta: dict | None = None) -> Event:
        if kind not in _KINDS:
            raise ValueError(f"unknown event kind: {kind!r}")
        ev = Event(kind=kind, who=who, content=" ".join((content or "").split()),
                   t_utc=t_utc or utc_now(), seq=self._seq, subject=subject, predicate=predicate,
                   object=object, modality=modality, meta=meta or {})
        self._seq += 1
        self._events.append(ev)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
        return ev

    def ingest_transcript(self, transcript: str, *, modality: str = "text") -> list[Event]:
        """THE FIX: a multi-party transcript becomes a run of first-class utterance events on the one
        timeline (was opaque text the router could not place). Each 'Speaker X: ...' is one node.
        They share the current UTC instant but keep distinct seq, preserving spoken order."""
        out = []
        for who, said in _SPEAKER.findall(transcript or ""):
            out.append(self.record("utterance", said, who=f"speaker_{who.upper()}", modality=modality))
        return out

    # ---------------------------------------------------------------- read (walk the one axis)
    def all(self) -> list[Event]:
        return list(self._events)

    def by_kind(self, kind: str) -> list[Event]:
        return [e for e in self._events if e.kind == kind]

    def utterances(self) -> list[Event]:
        return self.by_kind("utterance")

    def latest(self, kind: str | None = None) -> Event | None:
        seq = [e for e in self._events if kind is None or e.kind == kind]
        return seq[-1] if seq else None

    def since(self, t_utc: str) -> list[Event]:
        return [e for e in self._events if e.t_utc >= t_utc]

    def window(self, start_utc: str, end_utc: str) -> list[Event]:
        return [e for e in self._events if start_utc <= e.t_utc <= end_utc]

    # ---------------------------------------------------------------- adjust / re-examine
    # The timeline is not just append-only: ATANOR can revisit, correct, and re-check the past
    # (owner: "adjustable back and forth"). Revisions are themselves recorded as events (never a
    # silent overwrite -- the original stays auditable), so the record of WHAT WAS BELIEVED WHEN is
    # preserved. as_of() reconstructs the timeline's belief as it stood at a past instant.
    def revise(self, target_seq: int, new_content: str, *, reason: str = "") -> Event:
        """Record that a prior event's content is now corrected -- keeps the original, appends the
        revision (bitemporal spirit: valid change is a new fact, recorded_at is now)."""
        prior = next((e for e in self._events if e.seq == target_seq), None)
        if prior is None:
            raise KeyError(f"no event with seq {target_seq}")
        return self.record(prior.kind, new_content, who=prior.who, subject=prior.subject,
                           predicate=prior.predicate, object=prior.object, modality=prior.modality,
                           meta={"revises_seq": target_seq, "reason": reason})

    def retract(self, target_seq: int, *, reason: str = "") -> Event:
        """Record that a prior event no longer holds (e.g. a claim withdrawn). The original stays."""
        prior = next((e for e in self._events if e.seq == target_seq), None)
        if prior is None:
            raise KeyError(f"no event with seq {target_seq}")
        return self.record(prior.kind, "", who=prior.who, subject=prior.subject,
                           predicate=prior.predicate, object=prior.object, modality=prior.modality,
                           meta={"retracts_seq": target_seq, "reason": reason})

    def current_view(self) -> list[Event]:
        """The events that still stand: an original is dropped if a later revise/retract supersedes
        it; a revision replaces its target in place (so re-examination yields the corrected past)."""
        superseded = set()
        replacement: dict[int, Event] = {}
        for e in self._events:
            r = e.meta.get("revises_seq")
            x = e.meta.get("retracts_seq")
            if r is not None:
                superseded.add(r); replacement[r] = e
            if x is not None:
                superseded.add(x)
        out = []
        for e in self._events:
            if e.seq in replacement:
                out.append(replacement[e.seq])            # show the corrected version in place
            elif e.seq in superseded or e.meta.get("revises_seq") is not None \
                    or e.meta.get("retracts_seq") is not None:
                continue                                   # dropped original / the revision-marker itself
            else:
                out.append(e)
        return out

    def as_of(self, t_utc: str) -> list[Event]:
        """Re-check the past: the events on record at or before a past instant (belief as it stood)."""
        return [e for e in self._events if e.t_utc <= t_utc]

    def __len__(self) -> int:
        return len(self._events)


# A process-wide default timeline other organs can share (the ONE line). Callers may also hold their
# own Timeline for isolated contexts (e.g. one ITT game), but the default is the shared spine.
_DEFAULT: Timeline | None = None


def default_timeline() -> Timeline:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Timeline()
    return _DEFAULT
