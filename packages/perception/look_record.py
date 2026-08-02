# -*- coding: utf-8 -*-
"""What the eye has been seeing, in a form the rest of the system can read.

    from packages.perception.look_record import note, shortfall

THE DOOR THIS OPENS, and the measurement that said it was missing. `reflection_depth` counted fifteen
self-records and found ONE that a world-facing organ reads. The self-model is a well-connected loop
that mostly talks to itself: defect ledgers read by cycle ledgers read by parameter searches, all of
it about the repair machinery, none of it about what ATANOR is actually looking at. Meanwhile the eye
kept its looks in a `deque(maxlen=64)` that dies with the process, so the one organ facing the world
produced nothing anybody could read at all.

So the eye gets a record, and the record is about the thing that is actually going wrong: it keeps
seeing things it cannot name.

NO FRAME IS STORED, and that is not a privacy compromise but the same rule the eye already keeps. A
look is reduced to a handful of counts and the pixels are dropped, exactly as `eyes.grab` promises.
What survives is how surprising it was and how much of it went unnamed -- facts about ME, not about
the room.

WRITTEN AND READ, in that order and both of them. Today produced fifteen instances of building
something and never wiring it, and one inverse case -- records three organs read while nothing writes
them. A ledger nobody consults would be the sixteenth. `shortfall` is what interoception reads, so a
run of unnameable views becomes a felt deficit rather than a statistic.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "data" / "perception" / "looks.jsonl"
MAX_LINES = 2000


def note(reading: dict, named: dict | None = None) -> None:
    """One look, reduced to what it says about me."""
    named = named or {}
    rec = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "unexplained": round(float(reading.get("magnitude") or 0.0), 3),
        "my_own_doing": round(float(reading.get("self_explained") or 0.0), 3),
        "things": int(named.get("regions") or 0),
        "named": int(sum(c for _n, c in (named.get("names") or []))),
        "declined": int(named.get("declined") or 0),
        "vocabulary": int(named.get("vocabulary") or 0),
    }
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        lines = LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []
        lines.append(json.dumps(rec, ensure_ascii=False))
        LOG.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def recent(n: int = 40) -> list:
    if not LOG.exists():
        return []
    out = []
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def shortfall(n: int = 40) -> dict | None:
    """The deficit worth feeling: things seen that could not be called anything.

    Returns None when there is nothing to say -- no looks yet, or nothing seen. Silence rather than a
    zero, because a zero here would read as 'naming is fine' when the truth is 'I have not looked'.

    The share is reported rather than judged against a threshold I would have to invent. Interoception
    can weigh it; this only has to be honest about what happened."""
    rows = [r for r in recent(n) if r.get("things")]
    if not rows:
        return None
    things = sum(r["things"] for r in rows)
    named = sum(r["named"] for r in rows)
    return {"looks": len(rows), "things_seen": things, "named": named,
            "unnameable_share": round(1.0 - named / max(1, things), 3),
            "vocabulary": max((r.get("vocabulary") or 0) for r in rows)}
