# -*- coding: utf-8 -*-
"""Bitemporal episodic memory -- PRODUCTION capability (promoted from B5-2 validation, 2026-07-19).

The audit was right that a mission-local store proves nothing about the product; so the validated
store now LIVES here, in the production episodic-memory package, and the B5-2 mission imports it
from production (not the other way round). Semantics (pre-registered, B5 charter):
  current(s,p) = latest non-retracted assert (entity deletes win);
  as_of(s,p,t) = belief AT t -- only events with valid-time <= t and only retractions whose
                 correction-time <= t (a future correction never rewrites a past belief);
  rumours never assert; private edges are viewer-scoped; pure-revert corrections carry no value.
Validated: 30x300 events, current 452/452, as-of 463/463 vs an out-of-process oracle, retraction/
privacy mutation tests RED on broken variants. Import as:
    from packages.episodic_memory.bitemporal import BitemporalMemory, Event
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    fid: str
    op: str                      # assert | correct | retract | delete | rumour | private
    s: str
    p: str = ""
    o: str = ""
    t: int = 0                   # valid-time: when the fact is TRUE in the world
    retracts: str = ""           # for op=correct: the fact id it retracts (retract+reassert)
    owner: str = ""              # for op=private: the only viewer allowed
    rt: int = -1                 # recorded-time (transaction-time): when WE learned it. -1 = unset,
                                 # filled at ingest with the arrival order so recorded_at is always
                                 # defined (either world-supplied, or "the order we came to know it").


# ---------------------------------------------------------------------------------------------------
# the store (interval model). REWRITTEN after the machine-sealed holdout (Radxa exam_001) proved the
# expunge model wrong: a `retract` ENDS a value's validity at its time, creating a GAP; a query in
# the gap must ABSTAIN, not fall back to a stale earlier value. Deletes are per-(s,p) when p is given.
#   value events: assert / correct(o!="") / private  -> set the value at their time
#   end events:   retract / correct(o=="")           -> clear the value (gap) at their time
#   delete(s,p)   clears just (s,p); delete(s) with no p clears the whole entity
# current = the value standing at the end of the timeline; as_of(t) = the value standing at time t.
#
# TWO-AXIS (true bitemporal, added 2026-07-20). Each event now also carries recorded-time `rt` (when
# we LEARNED it). `as_known(s,p,valid_t,rec_t)` answers "what did we believe was true at valid-time
# `valid_t`, using ONLY knowledge recorded up to `rec_t`?" -- so a late-arriving correction (higher
# `rt`) does NOT rewrite what we believed at an earlier recording time. The legacy single-axis paths
# (`current`/`as_of`, rec_cutoff=None) are BYTE-FOR-BYTE unchanged -- they ignore `rt` and keep the
# validated (valid-time, fid) ordering, so the 452/452 & 463/463 validation and every B5-2 test hold.
# ---------------------------------------------------------------------------------------------------
class BitemporalMemory:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._clock: int = 0

    def ingest(self, ev: Event) -> None:
        if ev.rt < 0:                        # unset -> recorded_at = arrival order (monotonic)
            ev.rt = self._clock
        self._clock += 1
        self.events.append(ev)

    def _state(self, s: str, p: str, viewer: str, cutoff: int | None,
               rec_cutoff: int | None = None) -> tuple[str, str] | None:
        """Replay the events for (s,p) in valid-time order up to `cutoff` and return the standing
        (value, fid), or None if the slot is empty (never set / retracted-into-a-gap / deleted).
        When `rec_cutoff` is given (two-axis query) only events RECORDED by then are visible, and
        same-valid-time writes are ordered by recorded-time so a later-learned correction wins; when
        it is None the legacy (valid-time, fid) ordering is used unchanged."""
        rel = []
        for e in self.events:
            if cutoff is not None and e.t > cutoff:
                continue
            if rec_cutoff is not None and e.rt > rec_cutoff:          # not yet learned at rec_cutoff
                continue
            if e.op == "delete" and e.s == s and e.p in ("", p):      # entity- or attribute-delete
                rel.append(e)
            elif e.s == s and e.p == p and e.op in ("assert", "correct", "retract", "private", "rumour"):
                rel.append(e)
        key = (lambda e: (e.t, e.fid)) if rec_cutoff is None else (lambda e: (e.t, e.rt, e.fid))
        val: tuple[str, str] | None = None
        for e in sorted(rel, key=key):
            if e.op in ("delete", "retract"):
                val = None                                            # validity ends -> gap
            elif e.op == "correct":
                val = (e.o, e.fid) if e.o != "" else None             # reassert, or pure revert=gap
            elif e.op == "rumour":
                continue                                              # unverified -> never a fact
            elif e.op == "private":
                if e.owner and e.owner != viewer:
                    continue                                          # not visible to this viewer
                val = (e.o, e.fid)
            else:                                                     # assert
                val = (e.o, e.fid)
        return val

    def current(self, s: str, p: str, viewer: str = "public") -> tuple[str, str] | None:
        return self._state(s, p, viewer, None)

    def as_of(self, s: str, p: str, t: int, viewer: str = "public") -> tuple[str, str] | None:
        return self._state(s, p, viewer, t)

    def as_known(self, s: str, p: str, valid_t: int | None, rec_t: int,
                 viewer: str = "public") -> tuple[str, str] | None:
        """True bitemporal query: the belief about valid-time `valid_t` (None = end of world) as it
        stood when only knowledge recorded up to `rec_t` was available."""
        return self._state(s, p, viewer, valid_t, rec_cutoff=rec_t)

    # -- compatibility shims for the B5-2 mission's telemetry (correct-op world) --------------------
    def _retracted(self, cutoff: int | None = None) -> set[str]:
        return {e.retracts for e in self.events
                if e.op == "correct" and e.retracts and (cutoff is None or e.t <= cutoff)}

    def _deleted_by(self, s: str, t: int | None) -> bool:
        return any(e.op == "delete" and e.s == s and e.p == "" and (t is None or e.t <= t)
                   for e in self.events)


SessionMemory = BitemporalMemory   # compatibility alias
