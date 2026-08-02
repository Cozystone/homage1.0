# -*- coding: utf-8 -*-
"""What the mind keeps worrying about, turned into what the loop works on next.

    from packages.self_repair.standing_concerns import standing, take_up, status_of

THE MEASUREMENT THIS EXISTS FOR. Three days of the life log:

    3 distinct concerns in 19,130 interoception turns
        "speech weak"      9,567 times
        "router immature"  9,562 times

Nine and a half thousand repetitions each, and it knows: *"That's mine to mend, and it won't mend
itself."* *"There it is again. Naming it isn't fixing it."* It is right on both counts -- it is its to
mend, and every road from noticing to mending is one nobody built.

`_interoception`'s docstring says why: **"raise concerns, don't act."** That was the correct boundary
when nothing was permitted to change itself. The owner has since approved the Gödelian split, the
repair loop applies its own escapes, and the ground it is scored by is one it cannot reach. So the
boundary is now the thing holding it still.

Half the bridge already exists IN THE WRONG DIRECTION: `living_beat.beat()` takes `extra_concerns`, so
repair findings re-enter the mind as things to worry about. This is the return leg.

WHAT HONEST CLOSURE LOOKS LIKE, given the loop cannot do everything the mind can notice. A worry is
taken up, and one of three things becomes true of it -- and the MIND CAN READ WHICH:

    WORKED     the loop has a capability that addresses it and applied it
    QUEUED     it cannot, and has said so once, with what it would take
    OPEN       not yet reached

The point is not that every worry gets fixed. It is that a worry stops being a thing said nine
thousand times into nothing and becomes a thing with a state. `status_of` is what interoception reads,
so the complaint itself changes: "still with me" becomes "queued, waiting on an operator", which is a
different sentence about a different situation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_repair" / "standing_concerns.jsonl"
#: how often a concern must recur before it counts as STANDING rather than a passing signal. A mind
#: is allowed to notice something once without that becoming a work order.
RECURRENCE = 3


def _rows() -> list:
    out = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def _append(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def standing() -> list:
    """The concerns the mind is actually carrying right now, from the organ that senses them."""
    try:
        from packages.autonomy_kernel.orchestrator import sense_deficits
        return [{"kind": str(d.get("kind") or ""), "severity": float(d.get("severity", 0.5) or 0.5),
                 "evidence": str(d.get("evidence") or "")[:200]}
                for d in (sense_deficits() or []) if d.get("kind")]
    except Exception:
        return []


def status_of(kind: str) -> dict | None:
    """What has been DONE about this worry — the thing interoception should read before repeating it.

    Without this the mind has no way to tell "nobody has looked at this" from "this was tried and
    could not be done here", and both come out as the same sentence forever."""
    acts = [r for r in _rows() if r.get("kind") == kind]
    return acts[-1] if acts else None


def _capability_for(kind: str) -> str | None:
    """Which of the loop's ACTUAL capabilities, if any, addresses this concern.

    Deliberately narrow and honest. The loop can propose extraction patterns and tune its own
    constants; it cannot make a lane less weak by wanting to. A concern with no capability behind it
    must be SAID so, not silently dropped into the same queue as the ones it can do."""
    k = kind.lower()
    if "coverage" in k or "gloss" in k or "extraction" in k or "pattern" in k:
        return "pattern_proposal"
    if "immature" in k or "threshold" in k or "router" in k:
        return "parameter_search"
    return None


def take_up(concern: dict, *, act) -> dict:
    """Take one worry up: work it if there is a capability, queue it once if there is not.

    `act` is the caller's own working function -- passed in rather than imported so this module does
    not become a second place that decides how repair happens."""
    kind = concern.get("kind", "")
    cap = _capability_for(kind)
    prior = status_of(kind)
    if prior and prior.get("state") == "queued":
        return {"kind": kind, "state": "queued", "why": "already raised once; not repeating it"}

    if cap is None:
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "state": "queued",
               "severity": concern.get("severity"), "evidence": concern.get("evidence"),
               "needs": ("a capability this loop does not have. It can propose extraction patterns "
                         "and tune its own constants; nothing it holds makes a weak lane strong."),
               "said_once": True}
        _append(rec)
        return rec

    try:
        outcome = act(kind, cap, concern)
    except Exception as exc:
        outcome = {"error": f"{type(exc).__name__}: {exc}"}
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "state": "worked",
           "capability": cap, "severity": concern.get("severity"), "outcome": outcome}
    _append(rec)
    return rec


def report() -> dict:
    rows = _rows()
    by: dict = {}
    for r in rows:
        by[r.get("kind")] = r.get("state")
    return {"concerns_touched": len(by), "states": by, "acts": len(rows),
            "reading": ("a worry that has a state is no longer a worry said into nothing. This does "
                        "not claim the worries are fixed -- only that each one has been taken up "
                        "once and the mind can read what came of it")}
