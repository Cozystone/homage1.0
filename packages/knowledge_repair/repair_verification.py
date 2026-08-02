# -*- coding: utf-8 -*-
"""Did the repair hold? Ask the world, by whether the symptom comes back during ordinary use.

The owner's formulation (2026-07-28): someone who decides to train does not wear a muscle patch --
partly conscience, but structurally because "there is essentially no progress". The patch fails the
next time a box has to be lifted. Not because an inspector checks, but because THE WORLD ASKS
AGAIN.

That is the anti-cheat this module implements: THE TRIGGER IS THE VERIFIER. A repair is confirmed
by the original symptom ceasing to recur in live traffic, never by a score the repairer computes.

WHY THIS SIGNAL AND NOT COVERAGE. `purification.coverage` is a fine progress measure and a poor
verifier, because it is gameable from inside: loosen marker matching and more edges "place",
raising coverage without placing anything correctly. Hit-recurrence cannot be gamed that way -- a
loose attribution still yields wrong answers, so the conflict keeps firing during use and the
hit count keeps climbing. The dishonest repair scores BETTER on the internal metric and WORSE on
this one, which is the property worth having.

Its honest weakness is the mirror image, and it is stated rather than hidden: silence is not proof.
A conflict may stop recurring because nobody asked, not because it was fixed. So `verdict` reports
`unproven` when exposure was too thin, and never upgrades that to success. A verifier that counts
"no one tested me" as passing would be the very cheat it exists to catch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Below this many post-repair sightings-or-opportunities, absence of recurrence says nothing.
MIN_EXPOSURE = 3


@dataclass(frozen=True)
class RepairVerdict:
    """What live traffic says about a repair claimed for one subject/predicate."""
    subject: str
    predicate: str
    hits_before: int
    hits_after: int
    exposure_after: int          # how many times ANY conflict fired after the claim
    verdict: str                 # "held" | "recurred" | "unproven"

    @property
    def held(self) -> bool:
        return self.verdict == "held"

    def as_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "predicate": self.predicate,
                "hits_before": self.hits_before, "hits_after": self.hits_after,
                "exposure_after": self.exposure_after, "verdict": self.verdict}


def _rows(path=None) -> list[dict[str, Any]]:
    from packages.knowledge_repair.conflict_ledger import LEDGER
    try:
        src = path or LEDGER
        return [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _instant(text: str) -> datetime | None:
    """One ISO timestamp as a comparable instant, whichever writer produced it.

    This used to be a string comparison, justified as "correct for the fixed-width format the
    ledger writes" -- true only while one writer existed. The conflict ledger wrote naive local
    time and the repair driver wrote UTC with an offset, so `"...T19:38:29"` sorted after
    `"...T13:03:06+00:00"` although it happened nine hours EARLIER. Every repair was then graded
    `recurred` regardless of what it did, which is the safe direction and still useless: nothing
    could ever be credited.

    A naive stamp is read as local time because that is what the writer meant by it. Legacy rows
    therefore land where they actually belong instead of being shifted by the local offset."""
    try:
        dt = datetime.fromisoformat(str(text).strip())
    except (TypeError, ValueError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def verify(subject: str, predicate: str, claimed_at: str, *, path=None) -> RepairVerdict:
    """Split the ledger at the repair claim and read what happened afterwards."""
    rows = _rows(path)
    claim = _instant(claimed_at)
    before = after = exposure = 0
    for r in rows:
        ts = _instant(str(r.get("ts", "")))
        same = (str(r.get("subject", "")) == subject
                and str(r.get("predicate", "")) == predicate)
        # An unreadable stamp counts as BEFORE: it cannot be evidence that a repair came undone.
        if claim is None or ts is None or ts < claim:
            before += int(same)
        else:
            exposure += 1
            after += int(same)

    if after > 0:
        verdict = "recurred"
    elif exposure >= MIN_EXPOSURE:
        verdict = "held"
    else:
        verdict = "unproven"
    return RepairVerdict(subject, predicate, before, after, exposure, verdict)


def verify_all(claims: dict[tuple[str, str], str], *, path=None) -> list[RepairVerdict]:
    """Verdicts for every claimed repair, worst news first -- a repair that silently came undone
    is more urgent than one still awaiting exposure."""
    order = {"recurred": 0, "unproven": 1, "held": 2}
    out = [verify(s, p, ts, path=path) for (s, p), ts in claims.items()]
    return sorted(out, key=lambda v: (order[v.verdict], -v.hits_after))
