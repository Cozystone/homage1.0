# -*- coding: utf-8 -*-
"""The missing wire: ATANOR's own measurements become defects, in the ledger the repair cycle reads.

    from packages.self_repair.self_measured import scan, emit
    for d in scan():          # run the harnesses, read what they say is broken
        emit(d)               # into data/self_repair/self_measured.jsonl

WHY THIS FILE EXISTS, stated as the measurement that demanded it. The improvement-cycle ledger records
`failures_found_by_atanor: 0/2` — every failure repaired this project has been found by a person. The
self-repair loop itself is real and closed (`self_repair.repair_cycle`), but its ONLY input is
`defect_ledger.SOURCES`, which is `advisor_loop/comprehensive_review.jsonl` and `dialogue_coach.jsonl`
— complaints from other minds. ATANOR's own harnesses measure real failures every day and none of them
could reach the loop, because nothing carried them there.

That is the same pathology found three times today: the organ is built, and one wire is missing.

WHAT A MEASURED DEFECT MUST CARRY, and why each field is required rather than nice:

    location    an edit needs somewhere to go. The advisor ledger already learned this -- a critique
                that reads concrete but names nowhere is not repairable, and guessing concreteness
                from prose failed there. A harness knows its own file, so it must say it.
    evidence    verbatim failing cases. A defect asserted without instances is an opinion.
    prediction  what must RISE if this is really the fault. Makes the defect falsifiable BEFORE work
                starts, which is the same discipline the sealed gates run under.
    guard       what must NOT FALL. This is the anti-wireheading clause and it is the reason this
                file is not simply an emitter.

THE GUARD EXISTS BECAUSE THE FAILURE MODE IS REAL AND WAS OBSERVED. In cycle E5-2 the miss ranking
named `consisting of` as the largest single class of failures -- 49 of them, the obvious next fix. The
glosses behind it are "millennium: consisting of one thousand years", "United States: consisting of
fifty states". Mapping that to `made_of` would have raised the harness score while asserting that a
country is MADE OF its states. A loop that optimises its own metric without judgment does exactly that.

AND THE HONEST LIMIT, which matters more than the mechanism: **the guard does not catch that case.** A
guard can only watch metrics that exist, and no metric here measures "is this the right RELATION". The
ConceptNet agreement check would not have flagged it either, because it holds no entry for
`United States made_of fifty states` to disagree with. So a self-measured defect is a proposal that
still needs judgment; what this file closes is the FINDING station, not the loop.

Concretely: this can move `failures_found_by_atanor` off zero, which is the measured bottleneck. It
cannot move `capacity_cycles`, and claiming otherwise would be the exact overclaim the cycle ledger was
built to make impossible.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_repair" / "self_measured.jsonl"


@dataclass
class MeasuredDefect:
    """A fault ATANOR found in itself, in a form an edit can act on and a gate can refute."""

    key: str                       # what is wrong, in one line
    metric: str                    # the harness metric that shows it, named so it can be re-run
    observed: float                # its value now
    location: str                  # the file an edit would reach; without this, not repairable
    evidence: list = field(default_factory=list)     # verbatim failing cases
    prediction: str = ""           # what must RISE if this is the fault
    guard: str = ""                # what must NOT FALL -- the anti-wireheading clause
    found_by: str = "atanor"       # the field the improvement-cycle ledger counts
    at: float = field(default_factory=time.time)

    @property
    def repairable(self) -> bool:
        """A defect is actionable only with somewhere to cut, something to show, and a way to be
        wrong. Missing any of the three, it is an observation."""
        return bool(self.location and self.evidence and self.prediction)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["repairable"] = self.repairable
        return d


def _gloss_lane() -> list[MeasuredDefect]:
    """Read the gloss harness's own report and turn its ranked misses into defects.

    The harness is run as a subprocess rather than imported so the defect quotes a number that was
    actually produced, not one recomputed here with a different slice."""
    report = REPO / "data" / "perception" / "gloss_lane_recall.json"
    if not report.exists():
        try:
            subprocess.run([sys.executable, "scripts/gloss_lane_recall.py", "--sample", "40000"],
                           cwd=REPO, capture_output=True, timeout=1800)
        except Exception:
            return []
    if not report.exists():
        return []
    r = json.loads(report.read_text(encoding="utf-8"))
    recall = float(r.get("cue_recall", 0.0))
    out: list[MeasuredDefect] = []
    if recall < 0.9:
        missed = r.get("top_missed_cues") or []
        top = ", ".join(f"{c} ({n})" for c, n in missed[:5])
        out.append(MeasuredDefect(
            key=f"gloss lane misses {1 - recall:.0%} of glosses that visibly state a property",
            metric="gloss_lane_recall.cue_recall",
            observed=round(recall, 4),
            location="packages/graph_scale/property_extraction.py",
            evidence=[f"largest missed cue classes: {top}",
                      f"{r.get('cue_bearing_glosses')} cue-bearing glosses in the slice, "
                      f"{r.get('rows')} rows extracted"],
            prediction="cue_recall rises on the same deterministic slice",
            guard=("ConceptNet agreement must not fall, AND a new cue may not be mapped to a "
                   "relation it does not mean -- see `consisting of`, which is has_part"),
        ))
    return out


#: harnesses that can report on themselves. Each returns MeasuredDefects or nothing; a harness with no
#: complaint is silence, not a defect with severity zero.
SCANNERS = (_gloss_lane,)


def scan() -> list[MeasuredDefect]:
    """Every fault ATANOR's own harnesses currently report. Read-only."""
    out: list[MeasuredDefect] = []
    for fn in SCANNERS:
        try:
            out.extend(fn() or [])
        except Exception:
            continue                      # a broken scanner is silence, never a fabricated defect
    return out


def emit(defect: MeasuredDefect) -> None:
    """Append to the self-measured ledger. Append-only: a record that can be edited is a story."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(defect.as_dict(), ensure_ascii=False) + "\n")


def report() -> dict:
    """What the self-measured ledger holds, and how much of it an edit could actually reach."""
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return {"defects": len(rows),
            "repairable": sum(1 for r in rows if r.get("repairable")),
            "with_guard": sum(1 for r in rows if r.get("guard")),
            "found_by_atanor": sum(1 for r in rows if r.get("found_by") == "atanor"),
            "keys": [r.get("key") for r in rows[-6:]],
            "limit": ("finding is not judging: a guard watches metrics that exist, and no metric "
                      "here measures whether a proposed mapping means the right relation")}
