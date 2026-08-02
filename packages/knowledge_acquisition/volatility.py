# -*- coding: utf-8 -*-
"""Every fact learns its own refresh rate, so the tree re-grows only the branches that rot.

    led = VolatilityLedger("data/knowledge/volatility.json")
    led.observe(("tomatometer", "ratingvalue"), "83")      # -> Observation(changed=..., next_check=...)
    led.due(limit=500)                                     # what to re-fetch right now
    led.staleness(("trowel", "used_for"))                  # how old is what we would answer with

WHY THIS IS THE COST CONTROL AND NOT A REFINEMENT. A living graph that re-crawls everything on a fixed
cycle pays for the whole web every cycle forever. One that re-crawls each fact at ITS OWN rate pays only
for what moved. Most facts never move -- a trowel is used for spreading in every year there has been a
trowel -- and the ones that do are a small, identifiable minority: price, availability, ratingValue,
startDate. That ratio is the entire difference between an affordable live index and an unaffordable one,
and it is the one thing a general search engine structurally cannot do, because it never knew what it
extracted from a page.

THE ESTIMATOR is the standard Poisson change model (Cho and Garcia-Molina, 2000): assume changes arrive
at rate lambda, estimate it from changes seen per unit time, then check at roughly 1/lambda.

AND ITS BIAS, which must be stated because it decides whether the schedule is safe. Sampling can only see
changes it happens to catch: if a value changes five times between two checks, we record ONE change and
underestimate lambda by five. So the estimate is a LOWER BOUND on volatility and the schedule it produces
is systematically too slow for fast-moving facts. Two guards follow from that, and neither pretends the
bias is gone:
  * a change seen at consecutive checks HALVES the interval immediately rather than waiting for the
    average to catch up -- fast reaction to evidence of speed;
  * the predicate prior floors the interval for predicates the world is known to change, so a price is
    never scheduled yearly just because we have only ever seen it once.

WHAT IT DOES NOT KNOW. Whether a value that came back the same actually stayed the same, or changed and
changed back. Whether a source stopped updating. Whether the change was correction or news. It knows how
often what it sees is different from what it saw, which is all a schedule needs.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

HOUR = 3600.0
DAY = 24 * HOUR
YEAR = 365 * DAY

MIN_INTERVAL = 1 * HOUR
MAX_INTERVAL = 1 * YEAR
# First schedule before any change has been seen. The predicate name is the only evidence available,
# and it is a genuine one: schema.org calls a price a price.
PRIOR_INTERVAL = {
    "price": 6 * HOUR, "lowprice": 6 * HOUR, "highprice": 6 * HOUR,
    "availability": 6 * HOUR, "inventorylevel": 6 * HOUR,
    "ratingvalue": 1 * DAY, "reviewcount": 1 * DAY, "ratingcount": 1 * DAY,
    "aggregaterating": 1 * DAY, "position": 1 * DAY, "score": 1 * DAY,
    "startdate": 7 * DAY, "enddate": 7 * DAY, "eventstatus": 1 * DAY,
    "datemodified": 7 * DAY, "datepublished": 30 * DAY,
}
DEFAULT_INTERVAL = 90 * DAY


def _h(value: str) -> str:
    return hashlib.blake2b(str(value).strip().lower().encode("utf-8"), digest_size=8).hexdigest()


@dataclass
class FactHistory:
    """Compressed history of one fact: enough to estimate a rate, not enough to be a log."""

    first_seen: float
    last_seen: float
    last_hash: str
    observations: int = 1
    changes: int = 0
    last_change: float = 0.0
    interval: float = DEFAULT_INTERVAL

    def rate(self) -> float:
        """Changes per second, a LOWER BOUND -- see the module docstring on sampling bias."""
        span = self.last_seen - self.first_seen
        return (self.changes / span) if span > 0 and self.changes else 0.0


@dataclass
class Observation:
    key: tuple
    changed: bool
    interval: float
    next_check: float
    observations: int
    changes: int


@dataclass
class VolatilityLedger:
    path: Path | str | None = None
    facts: dict = field(default_factory=dict)          # "subject|predicate" -> FactHistory
    _dirty: bool = False

    def __post_init__(self) -> None:
        if self.path and Path(self.path).exists():
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
            self.facts = {k: FactHistory(**v) for k, v in raw.get("facts", {}).items()}

    # ---- the schedule ---------------------------------------------------------------------------
    @staticmethod
    def _prior(predicate: str) -> float:
        return PRIOR_INTERVAL.get(predicate.strip().lower(), DEFAULT_INTERVAL)

    def _schedule(self, h: FactHistory, predicate: str, changed: bool) -> float:
        floor = min(self._prior(predicate), MAX_INTERVAL)
        if changed:
            # evidence of speed beats the running average: react now, converge later
            nxt = max(MIN_INTERVAL, h.interval / 2.0)
        else:
            rate = h.rate()
            if rate > 0:
                nxt = 1.0 / rate                        # Cho & Garcia-Molina: check at ~1/lambda
            else:
                nxt = min(h.interval * 1.5, MAX_INTERVAL)   # nothing has moved; back off gently
        # the prior FLOORS a predicate the world is known to change, so one quiet observation of a
        # price cannot schedule it yearly
        return float(max(MIN_INTERVAL, min(nxt, floor if predicate.lower() in PRIOR_INTERVAL
                                           else MAX_INTERVAL)))

    # ---- the two operations ----------------------------------------------------------------------
    def observe(self, key: tuple, value: str, at: float | None = None) -> Observation:
        """Record what a fact looks like now. Returns whether it moved and when to look again."""
        at = float(at if at is not None else time.time())
        k = f"{key[0]}|{key[1]}"
        vh = _h(value)
        h = self.facts.get(k)
        if h is None:
            h = self.facts[k] = FactHistory(first_seen=at, last_seen=at, last_hash=vh,
                                            interval=self._prior(key[1]))
            self._dirty = True
            return Observation(key, False, h.interval, at + h.interval, 1, 0)
        changed = vh != h.last_hash
        h.observations += 1
        h.last_seen = at
        if changed:
            h.changes += 1
            h.last_change = at
            h.last_hash = vh
        h.interval = self._schedule(h, key[1], changed)
        self._dirty = True
        return Observation(key, changed, h.interval, at + h.interval, h.observations, h.changes)

    def due(self, now: float | None = None, limit: int = 1000) -> list[tuple]:
        """Facts whose next check has arrived, most overdue first. This IS the re-crawl queue."""
        now = float(now if now is not None else time.time())
        overdue = []
        for k, h in self.facts.items():
            due_at = h.last_seen + h.interval
            if due_at <= now:
                overdue.append((due_at - now, tuple(k.split("|", 1))))
        overdue.sort()
        return [k for _d, k in overdue[:limit]]

    def staleness(self, key: tuple, now: float | None = None) -> dict:
        """How old is what we would answer with, and how fast does this fact usually move.

        An answer that cannot say this is guessing about its own freshness. The point of the ledger is
        that ATANOR can say 'checked 8 seconds ago' or 'checked three weeks ago and it changes about
        weekly' instead of implying both are the same."""
        now = float(now if now is not None else time.time())
        h = self.facts.get(f"{key[0]}|{key[1]}")
        if h is None:
            return {"known": False}
        age = now - h.last_seen
        rate = h.rate()
        return {"known": True, "age_s": age, "age_h": round(age / HOUR, 2),
                "interval_h": round(h.interval / HOUR, 2),
                "observations": h.observations, "changes": h.changes,
                "changes_per_day": round(rate * DAY, 4) if rate else 0.0,
                "overdue": age > h.interval,
                "expected_changes_since_check": round(rate * age, 3) if rate else 0.0}

    # ---- persistence -------------------------------------------------------------------------------
    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"facts": {k: v.__dict__ for k, v in self.facts.items()}}),
                     encoding="utf-8")
        self._dirty = False

    def report(self) -> dict:
        if not self.facts:
            return {"facts": 0}
        moved = [h for h in self.facts.values() if h.changes]
        iv = sorted(h.interval for h in self.facts.values())
        return {"facts": len(self.facts),
                "ever_changed": len(moved),
                "share_volatile": round(len(moved) / len(self.facts), 4),
                "median_interval_days": round(iv[len(iv) // 2] / DAY, 2),
                "due_now": len(self.due()),
                # the number that decides the bill: what fraction of the graph needs re-fetching per day
                "refetch_per_day": round(sum(min(1.0, DAY / h.interval)
                                             for h in self.facts.values()), 1)}
