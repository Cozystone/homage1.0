# -*- coding: utf-8 -*-
"""The one thing the loop may change about itself: a NUMBER it already chose badly, never the logic.

    from packages.self_repair.tuning import apply_tuned, propose_tuning
    apply_tuned()        # load owner-approved tunings at startup
    propose_tuning(...)  # measure one, and write it only if the owner has opened that door

THE TENSION THIS EXISTS FOR, found by running the loop unattended rather than by reasoning about it.
Four cycles ran with nobody in them. Three plateaued, and all three DIAGNOSED THEIR OWN ESCAPE
correctly and identically: `pattern_proposer.evaluate:min_fire = 7`. Not one applied it, because that
constant lives in `packages/self_repair/`, which `provisional.FORBIDDEN` refuses -- and refuses for a
good reason, since that directory holds the judge, the gate and the ledger.

So the only escape the loop could find was inside the only code it may not touch. That is a real
collision between the safety boundary and RSI, and the wrong resolution is to widen the boundary: a
loop that may rewrite its own judge can pass anything by lowering the bar, which is the wirehead path
this project has refused all along.

WHAT IS ACTUALLY SAFE, and why this is a different act. Changing a numeric default is not changing
judgment logic, and the result is still scored by a measurement the loop cannot reach:
`scripts/gloss_lane_recall.py` and `improvement_cycles.py` stay forbidden, so a loosened proposal bar
buys nothing unless what comes through it survives a held-out gate the loop has no way to edit. The
loop can make itself more permissive; it cannot make itself look better.

FOUR THINGS BOUND IT, and they are the point rather than decoration:

    1. VALUES ONLY. A tuning is a number replacing a number. Names come from AST discovery over
       `parameter_space.ORGANS`; anything not found there is refused.
    2. MEASURED FIRST. A tuning is written only after enablement rises AND the held-out gate agrees.
    3. OWNER-GATED. Writing requires ATANOR_ALLOW_SELF_TUNING=1 in the environment. Unset, the loop
       proposes and records and changes nothing -- which is the state it ships in.
    4. REVERSIBLE BY DELETING ONE FILE. Every tuning lives in data/self_repair/tuned_parameters.json
       with the evidence that justified it. Delete it and the hand-picked defaults are back.

The honest limit: this closes the gap for CONSTANTS. An escape that needs a new organ, or a threshold
that ought to be a learned function rather than a number, is still outside what the loop can reach --
and widening THAT is not a config change, so it does not belong here.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TUNED = REPO / "data" / "self_repair" / "tuned_parameters.json"
#: the owner's switch. Unset is the shipped state: propose, measure, record, change nothing.
ENV_FLAG = "ATANOR_ALLOW_SELF_TUNING"

#: THE GROUND. Owner approved the Goedelian split on 2026-08-01 -- "may not touch the ground" is now a
#: different rule from "may not touch itself", and the loop may tune its own constants. Defining the
#: ground is the other half of that decision, and the half that makes it safe rather than merely open.
#:
#: Goedel's sentence is productive because its TRUTH is settled outside the system. Everything here is
#: that outside. If the loop could reach any of it, the split would not be a tangled hierarchy; it
#: would be a system marking its own exam:
#:
#:   the harness      it would tune the measurement instead of the thing measured
#:   the ledgers      it would rewrite the record of what it did
#:   the accountability organs  it would erase the commitments R holds it to, or set the friction to
#:                    zero -- R with a self-editable cost is not accountability, it is a formality
#:   the moral core   not negotiable at any level
#:
#: A tuning proposal naming anything under these is refused before it is measured, so a green can
#: never be bought by moving the thing that says green.
GROUND = (
    "scripts/gloss_lane_recall.py",
    "scripts/e5_",
    "packages/meta_diagnosis/improvement_cycles.py",
    "packages/self_repair/criteria_ledger.py",
    "packages/self_repair/normative_accountability.py",
    "packages/self_repair/provisional.py",
    "packages/self_repair/tuning.py",
    "packages/conformal_gate/",
    "packages/moral",
)


def on_ground(path: str) -> str | None:
    """Why this may never be tuned, or None if it is the loop's own business."""
    p = str(path).replace("\\", "/")
    for g in GROUND:
        if p.startswith(g):
            return (f"{p} is under '{g}', which is the GROUND: the part that settles whether the "
                    f"loop's claims are true. Tuning it would be marking its own exam")
    return None


def writes_allowed() -> bool:
    return os.environ.get(ENV_FLAG, "") == "1"


def tuned() -> dict:
    if not TUNED.exists():
        return {}
    try:
        return {k: v["value"] for k, v in json.loads(TUNED.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def apply_tuned() -> dict:
    """Rebind every owner-approved tuning. Called once at loop startup; silent when there are none."""
    from packages.self_repair.parameter_space import _set_default, discover

    want = tuned()
    if not want:
        return {"applied": 0}
    by_key = {p.key(): p for p in discover()}
    applied = []
    for key, value in want.items():
        p = by_key.get(key)
        if p is None:                              # the knob moved or was deleted; refuse to guess
            continue
        if _set_default(p, value) is not None:
            applied.append(f"{key}={value}")
    return {"applied": len(applied), "keys": applied}


def propose_tuning(key: str, value, *, enablement: int, gate_rise: float | None,
                   evidence: str = "") -> dict:
    """Record a measured tuning, and write it only if the owner has opened that door.

    A refusal here is the normal outcome and is recorded as one, so the ledger shows what the loop
    WANTED to change as well as what it was allowed to."""
    from packages.self_repair.parameter_space import discover

    found = {p.key(): p for p in discover()}
    if key not in found:
        return {"written": False, "why": f"{key} is not a discovered constant; values only"}
    grounded = on_ground(found[key].file)
    if grounded:
        return {"written": False, "why": grounded, "refused_as": "ground"}
    if enablement <= 0:
        return {"written": False, "why": "unlocked nothing, so there is nothing to justify it"}
    if gate_rise is None or gate_rise <= 0:
        return {"written": False, "why": "the held-out gate did not agree; enablement alone is not "
                                         "evidence, it is only a reason to ask the gate"}
    rec = {"value": value, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "enablement": enablement,
           "gate_rise": round(float(gate_rise), 6), "evidence": evidence}
    if not writes_allowed():
        return {"written": False, "would_have_written": {key: rec},
                "why": f"{ENV_FLAG} is not set. The loop measured this, wants it, and may not have "
                       f"it -- which is the shipped state, not a failure"}
    cur = {}
    if TUNED.exists():
        try:
            cur = json.loads(TUNED.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    cur[key] = rec
    TUNED.parent.mkdir(parents=True, exist_ok=True)
    TUNED.write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"written": True, key: rec}
