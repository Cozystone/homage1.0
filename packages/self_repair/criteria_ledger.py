# -*- coding: utf-8 -*-
"""Criteria this system once held and gave up — kept so that later judgment cannot re-adopt them.

    from packages.self_repair.criteria_ledger import abandon, check, guard

    guard("beats_both_parts")        # raises: this criterion was defeated, here is the case
    check("n_rows")                  # -> the reason, or None if the criterion is still held

M2, THE THIRD CONDITION. The Axiom of Self asks for three things and this system had two: it
adjudicates norms (the judge returns accept, refuse, or refuse-for-lack-of-history) and it can
rearrange its own criteria (seventeen discovered by AST). The missing one is that **a criterion
abandoned has to survive, with its reason, in a form later judgment reads** -- otherwise every
adjudication is forgotten and the same defeated standard walks back in.

That is not hypothetical here. On 2026-08-01 four criteria were adjudicated and dropped in a single
session, each defeated by a specific case:

    "a pair beats both its parts"     two INDEPENDENT moves satisfy this for free -- a move worth 2
                                      and a move worth 1 give a pair worth 3, and 3 beats both. It
                                      read GREEN on addition.
    "six calibration pairs is n=6"    six rows held TWO values; one cue proposed for four relations
                                      gives four identical recall deltas, because recall sees the
                                      regex and never the relation label.
    "proxy recall at offset 500000"   that is the GATE's own slice. A predictor evaluated on the rows
                                      it predicts is not a predictor.
    "the cycle says atanor found it"  five cycles claimed it while applying nothing, reverting
                                      nothing and surfacing nothing.

Every one of those was written down -- in commit prose and module docstrings, where nothing can read
it. Prose is a photograph of a judgment. This is the cartridge.

WHAT MAKES IT A LOOP RATHER THAN A DIARY, which is the whole distinction this project measured at
2-of-14 this morning: the ledger is CONSUMED. `moves.apply_pair` asks it before scoring composition
and `cheap_proxy.calibration` asks it before reporting an n. A record nobody reads changes nothing,
however well kept.

WHAT IT DELIBERATELY DOES NOT DO. It does not forbid REVISITING a criterion -- `readopt` exists, it
requires a reason, and it leaves both the abandonment and the return in the history. A system that
could never change its mind twice would not be adjudicating, it would be sulking. What it forbids is
re-adopting one SILENTLY.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_repair" / "abandoned_criteria.jsonl"


class CriterionAbandoned(Exception):
    """Raised when code reaches for a standard this system already defeated."""


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


def abandon(name: str, *, asserted: str, defeated_by: str, successor: str = "",
            found_by: str = "atanor") -> dict:
    """Record a criterion this system is giving up, and the case that defeated it.

    `defeated_by` is required and is the load-bearing field: a criterion dropped without a case is a
    mood, and a mood cannot constrain a later judgment."""
    if not defeated_by.strip():
        raise ValueError("a criterion abandoned without the case that defeated it is not an "
                         "adjudication; it is a preference")
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "criterion": name, "act": "abandon",
           "asserted": asserted, "defeated_by": defeated_by, "successor": successor,
           "found_by": found_by}
    _append(rec)
    return rec


def readopt(name: str, *, because: str) -> dict:
    """Take a criterion back. Allowed, recorded, never silent."""
    if not because.strip():
        raise ValueError("re-adopting a defeated criterion requires the reason it is safe now")
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "criterion": name, "act": "readopt",
           "because": because}
    _append(rec)
    return rec


def status(name: str) -> dict | None:
    """The most recent act on this criterion, or None if it was never adjudicated."""
    acts = [r for r in _rows() if r.get("criterion") == name]
    return acts[-1] if acts else None


def check(name: str) -> str | None:
    """The reason this criterion is not to be used, or None if it may be.

    Returns the REASON rather than a bool, because M2 asks that the why be reusable -- a caller that
    only learns 'no' has to reinvent the argument, which is how a defeated standard comes back."""
    last = status(name)
    if not last or last.get("act") != "abandon":
        return None
    s = last.get("successor")
    return (f"{last['criterion']} was abandoned: {last['defeated_by']}"
            + (f" Use instead: {s}" if s else ""))


def guard(name: str) -> None:
    """Refuse outright. For code paths where continuing on a defeated criterion is the bug."""
    why = check(name)
    if why:
        raise CriterionAbandoned(why)


def in_force(name: str, *, default: str) -> dict:
    """Which standard actually governs here — the ledger is the authority, not the call site.

    This is what makes the ledger a LOOP rather than a record. A consumer does not hardcode the
    criterion it applies; it asks. If the criterion was defeated, the successor governs and the
    defeating case travels with the answer, so a reader of the result can see WHY this standard and
    not the obvious one. If it was never adjudicated, or was taken back, the default governs."""
    why = check(name)
    return {"criterion": (status(name) or {}).get("successor") or default if why else default,
            "superseded": bool(why), "because": why}


def history() -> dict:
    rows = _rows()
    live = {r["criterion"] for r in rows if r.get("act") == "readopt"}
    abandoned = sorted({r["criterion"] for r in rows if r.get("act") == "abandon"} - live)
    return {"acts": len(rows), "criteria_abandoned": len(abandoned), "abandoned": abandoned,
            "readopted": sorted(live), "rows": rows,
            "reading": ("a criterion here is not an opinion about the world; it is a standard this "
                        "system applied to ITSELF and then defeated with a case")}
