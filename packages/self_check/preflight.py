# -*- coding: utf-8 -*-
"""The four checks ATANOR runs on itself before believing a measurement.

Owner, 2026-07-29: 3대 사전검사를 ATANOR가 자기 자신에게 직접 돌리는 루프를 완성하자.
자가진화도 관리자 승인 안 받게 풀어주고.

WHAT THE OPERATOR WAS ACTUALLY DOING, and why it can be replaced but not simply removed. Five times
in one day this system was maximally confident and completely wrong, and not one of those was caught
from the inside:

    an occluded browser window reported as CitySample     phase-correlation confidence 0.999
    a border artefact used to order windows                an UNTRAINED net scored 0.794
    object discovery in a city with no traffic in it       400 frames, 0 dropped, clean maps
    every view matched to one stored instance              264/264 "recognised"
    re-identification validated pairwise                   93%, against 15.5% at real scale

Each was caught by an outside instrument: a person looking at a screenshot, noticing a number that
could not be true, counting mover pixels, asking the window manager who owned them. That is the job
the operator's signature was doing — not judgement about goals, but an independent measurement.

So the way to take the operator out of the loop is not to delete the gate. It is to give the gate to
these checks, and then to require that they EARN it by catching the five failures above before they
are allowed to sign anything (`scripts/self_check_retro.py`).

    I  integrity      is the sensor looking at what it thinks it is looking at
    D  data           does the thing being sought EXIST in this data, above its base rate
    R  resolution     is it LARGER than the smallest unit the answer can express
    X  discriminator  does the instrument separate real from random, against a control

INCONCLUSIVE COUNTS AS FAILURE, and this is the load-bearing rule. Four of the five failures passed
because the check was ABSENT, not because it was passed. A gate that scores "could not check" as
green is a gate with a hole in exactly the shape of a shortcut, and a system optimising against it
will find that hole faster than it finds the truth.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ANCHORED TO THE REPOSITORY, NOT THE WORKING DIRECTORY. As a relative path this resolved against
# wherever the process happened to start, so running a scorer from C:\WINDOWS\system32 tried to create
# `system32\data\self_check\` -- an audit ledger scattering itself across the filesystem, and writing
# into a system directory at that. The record of what a gate refused is only useful if it all lands in
# one place.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "self_check" / "preflight.jsonl"


@dataclass
class Check:
    """One question, its answer, and whether it could be answered at all."""

    name: str
    passed: bool
    ran: bool
    detail: str = ""
    value: float | None = None

    @property
    def green(self) -> bool:
        """Inconclusive is not green. See the module docstring — this is the whole design."""
        return self.ran and self.passed

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.name, "green": self.green, "ran": self.ran,
                "passed": self.passed, "value": self.value, "detail": self.detail[:200]}


@dataclass
class Verdict:
    """What the four checks together permit."""

    claim: str
    checks: list[Check] = field(default_factory=list)

    @property
    def may_promote(self) -> bool:
        need = {"integrity", "data", "resolution", "discriminator"}
        got = {c.name for c in self.checks if c.green}
        return need.issubset(got)

    def why_not(self) -> list[str]:
        out = []
        for n in ("integrity", "data", "resolution", "discriminator"):
            c = next((c for c in self.checks if c.name == n), None)
            if c is None:
                out.append(f"{n}: NOT RUN — inconclusive counts as failure")
            elif not c.ran:
                out.append(f"{n}: could not run ({c.detail})")
            elif not c.passed:
                out.append(f"{n}: failed ({c.detail})")
        return out

    def as_dict(self) -> dict[str, Any]:
        return {"claim": self.claim, "may_promote": self.may_promote,
                "checks": [c.as_dict() for c in self.checks], "blocked_by": self.why_not()}


# --- the four checks --------------------------------------------------------------------------------

def integrity(observed_source: str | None, intended_source: str | None,
              visible_frac: float | None = None, min_visible: float = 0.9) -> Check:
    """Is the sensor looking at what it thinks it is looking at?

    The eye reports `occluded`, `occluded_by` and `visible_frac` for exactly this. Four captures were
    diagnosed as a wrong turn rate while the eye was returning a browser."""
    if observed_source is None and visible_frac is None:
        return Check("integrity", False, False, "no provenance reported by the sensor")
    if visible_frac is not None:
        ok = visible_frac >= min_visible
        return Check("integrity", ok, True, value=round(float(visible_frac), 3),
                     detail=f"{visible_frac:.0%} of the field is the intended source"
                            f"{'' if ok else f' (needs {min_visible:.0%})'}")
    ok = observed_source == intended_source
    return Check("integrity", ok, True, detail=f"saw {observed_source!r}, wanted {intended_source!r}")


def data(base_rate: float | None, min_rate: float = 0.01, n: int | None = None,
         min_n: int = 30) -> Check:
    """Does the thing being sought EXIST in this data, often enough to be found?

    Object discovery ran on a city where movers were 0.3% of a frame. The recordings were flawless by
    every other measure."""
    if base_rate is None:
        return Check("data", False, False, "base rate was never measured")
    if n is not None and n < min_n:
        return Check("data", False, True, value=round(float(base_rate), 4),
                     detail=f"only {n} instances (need {min_n}) — too few to conclude from")
    ok = base_rate >= min_rate
    return Check("data", ok, True, value=round(float(base_rate), 4),
                 detail=f"present at {base_rate:.2%}"
                        f"{'' if ok else f' — below the {min_rate:.0%} floor'}")


def resolution(target_size: float | None, unit_size: float | None, ratio: float = 2.0) -> Check:
    """Is the thing LARGER than the smallest unit the answer can express?

    The median mover was 16 px against a 1,280 px minimum group — eighty times too small. Both
    grouping versions were scored on failing to output something they structurally could not."""
    if target_size is None or unit_size is None:
        return Check("resolution", False, False, "target or unit size unmeasured")
    if unit_size <= 0:
        return Check("resolution", False, False, "unit size is zero")
    r = float(target_size) / float(unit_size)
    ok = r >= ratio
    return Check("resolution", ok, True, value=round(r, 3),
                 detail=f"target is {r:.2f}x the unit"
                        f"{'' if ok else f' — needs {ratio}x; the answer cannot express the thing'}")


def discriminator(same: Any = None, different: Any = None, *,
                  real_score: float | None = None, control_score: float | None = None,
                  overlap: float | None = None, max_overlap: float = 0.10) -> Check:
    """Does the instrument separate real from random?

    Two forms, because measurements come in two shapes. Give it same/different score populations and
    it computes the overlap; give it a real score and its control and it requires the real one to
    win. Either way the question is the same: could this instrument tell truth from noise if it were
    handed noise?"""
    import numpy as np

    if overlap is not None:
        ok = float(overlap) <= max_overlap
        return Check("discriminator", ok, True, value=round(float(overlap), 4),
                     detail=f"{overlap:.1%} of different-pairs score above the 10th percentile of "
                            f"same-pairs{'' if ok else f' (needs <={max_overlap:.0%})'}")
    if same is not None and different is not None:
        s, d = np.asarray(same, float), np.asarray(different, float)
        if len(s) < 10 or len(d) < 10:
            return Check("discriminator", False, False, f"too few scores ({len(s)}/{len(d)})")
        s10 = float(np.percentile(s, 10))
        ov = float(np.mean(d > s10))
        ok = ov <= max_overlap
        return Check("discriminator", ok, True, value=round(ov, 4),
                     detail=f"{ov:.1%} of different-pairs score above the 10th percentile of "
                            f"same-pairs{'' if ok else f' (needs <={max_overlap:.0%})'}")
    if real_score is not None and control_score is not None:
        lift = float(real_score) - float(control_score)
        ok = lift > 0
        return Check("discriminator", ok, True, value=round(lift, 4),
                     detail=f"real {real_score:.4f} vs control {control_score:.4f}, lift {lift:+.4f}"
                            f"{'' if ok else ' — the control matched or beat it'}")
    return Check("discriminator", False, False, "no control was measured")


# --- the loop ---------------------------------------------------------------------------------------

def run(claim: str, **kw: Any) -> Verdict:
    """Run all four on a claim and record the verdict, whatever it is.

    Everything is journalled including refusals, because the record of what was NOT allowed is the
    evidence that the gate is doing anything at all."""
    v = Verdict(claim=claim, checks=[
        integrity(kw.get("observed_source"), kw.get("intended_source"), kw.get("visible_frac")),
        data(kw.get("base_rate"), kw.get("min_rate", 0.01), kw.get("n"), kw.get("min_n", 30)),
        resolution(kw.get("target_size"), kw.get("unit_size"), kw.get("size_ratio", 2.0)),
        discriminator(kw.get("same"), kw.get("different"),
                      real_score=kw.get("real_score"), control_score=kw.get("control_score"),
                      overlap=kw.get("overlap"), max_overlap=kw.get("max_overlap", 0.10)),
    ])
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **v.as_dict()},
                            ensure_ascii=False) + "\n")
    return v


def gated(claim: str, promote: Callable[[], Any], **kw: Any) -> dict[str, Any]:
    """Promote WITHOUT a human, if and only if all four are green.

    This is the operator's signature replaced rather than removed. What the signature was doing was
    an independent measurement, and these are that measurement; what it was not doing was deciding
    whether the goal was worth pursuing, which was never gated anyway.

    The constitution and the moral core are not what this unlocks. It unlocks PROMOTION."""
    v = run(claim, **kw)
    if not v.may_promote:
        return {"promoted": False, "reason": v.why_not(), "verdict": v.as_dict()}
    try:
        result = promote()
    except Exception as exc:
        return {"promoted": False, "reason": [f"promotion raised: {exc}"], "verdict": v.as_dict()}
    return {"promoted": True, "result": result, "verdict": v.as_dict()}
