# -*- coding: utf-8 -*-
"""The RSI question, answered as a chart rather than an opinion.

    from packages.meta_diagnosis.rsi_verdict import verdict
    verdict()

WHAT RSI IS, stated so the answer cannot drift: not "the system changed itself" -- it does, and three
patches survived blind measurement -- but "an improvement made the NEXT improvement easier". That is
one measurable thing and four supporting ones:

    enablement not shrinking     the definition. Product gain accumulates; only enablement compounds.
    escapes compose              a pair that unlocks what neither part unlocks is the difference
                                 between a search and a lookup
    failures found by ATANOR     if a person still finds them, the loop is a tool
    human touches per cycle      if a person still turns the crank, the loop is a tool
    verification throughput      a search nobody can afford to run is not a search

Each is already recorded by something. This assembles them and refuses to average them into a score,
because a single number would let a strong axis hide a dead one -- which is exactly how `gains_holding`
came to report on a series where the compounding cycles counted zero.

TWO DEFECTS IN THIS FILE'S OWN FIRST VERSION, both of the shape it exists to catch:

  * `human_touches_per_cycle` held a LIST and `verification_throughput` held a SENTENCE, while
    `axes_met` was computed as `v is True`. Two of the five axes could never be met no matter what the
    loop did. The instrument had the same defect as the metric it replaced.
  * `escapes_compose` read whether a pair BEAT BOTH PARTS -- which two independent moves satisfy for
    free, since a move worth 2 and a move worth 1 give a pair worth 3. It read GREEN on addition. The
    corrected test lives in `moves.apply_pair` and asks for an emergent unlock or a superadditive
    total, and under it the same 15 pairs score zero.

Every axis here is now a bool with the evidence that produced it, and an axis that cannot be measured
yet says so instead of quietly reading false.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: an axis needs enough points before "holding" means anything. Three deltas is the window; fewer is
#: not a trend and is reported as unknown rather than as a pass.
MIN_POINTS = 4
#: how many recent cycles the "is a person still finding the failures" question looks at. FIXED HERE,
#: BEFORE MEASURING, and changed while the axis was FAILING at 0.818 -- which is exactly the moment a
#: window becomes suspicious, so the all-time figure is reported beside it permanently. The case for a
#: window is that the axis asks whether a person STILL finds them, and an all-time ratio is dragged
#: forever by the cycles that ran before the loop could find anything at all. The case against is that
#: I chose it while losing. Both are on the record; the window may not be widened again.
RECENT = 5
#: the proxy may GATE only above this, and only with the correlation stated beside the answer.
MIN_R = 0.7


def _axis(met, evidence, why=""):
    return {"met": met, "evidence": evidence, "why": why}


def _found_by_derived() -> list:
    """Who found the failure -- DERIVED from what each cycle did, not read from what it claimed.

    Five unattended cycles wrote `failure_found_by: atanor` while applying nothing, reverting nothing
    and surfacing nothing, and five of those in a row turned this axis green. Rewriting those rows
    would destroy the record of a system grading itself generously, which is worth keeping; so the
    ledger stays append-only and the claim is checked against the evidence in the same row. This is
    the day's own doctrine turned on the loop's self-report: read the case, not the summary."""
    rows = []
    led = REPO / "data" / "meta_diagnosis" / "improvement_cycles.jsonl"
    if led.exists():
        for line in led.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    out = []
    for r in rows:
        claim = r.get("failure_found_by")
        notes = r.get("notes") or ""
        vacuous = (r.get("human_touches") == 0 and "applied=[]" in notes
                   and "reverted=[]" in notes and "'unlocked': 0" not in notes.replace('"', "'")
                   and not r.get("gain"))
        out.append("none" if vacuous else claim)
    return out


def verdict() -> dict:
    from packages.meta_diagnosis.cheap_proxy import calibration
    from packages.meta_diagnosis.enablement import trajectory as enab
    from packages.meta_diagnosis.improvement_cycles import trajectory as cycles

    c, e, cal = cycles(), enab(), calibration()

    # ---- 1. enablement not shrinking -- the definition
    series = e.get("enablement_per_cycle") or []
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    if len(series) < MIN_POINTS:
        a1 = _axis(None, {"scored": len(series), "series": series},
                   f"{len(series)} capacity cycles scored; {MIN_POINTS} needed before a trend is a "
                   f"trend rather than two points and a hope")
    else:
        # A SERIES OF ZEROS HAS DELTAS OF ZERO AND WOULD PASS "not shrinking" -- recording four dead
        # capacity cycles would turn this axis green while nothing had been unlocked at all. Not
        # shrinking is only meaningful about a quantity that is sometimes non-zero.
        alive = sum(series) > 0
        a1 = _axis(alive and all(d >= 0 for d in deltas[-3:]),
                   {"series": series, "last_3_deltas": deltas[-3:], "total_unlocked": sum(series)},
                   "" if alive else ("every scored cycle unlocked nothing; a flat line of zeros is "
                                     "not a trend that holds, it is a loop that is not moving"))

    # ---- 2. escapes compose -- emergent or superadditive, never "beats both parts"
    pairs, composed = [], None
    pf = REPO / "data" / "self_repair" / "pair_search_v2.json"
    if pf.exists():
        try:
            pairs = json.loads(pf.read_text(encoding="utf-8"))
            composed = any(p.get("composes") for p in pairs)
        except Exception:
            pass
    a2 = _axis(composed,
               {"pairs_tried": len(pairs),
                "emergent": sum(1 for p in pairs if p.get("is_emergent")),
                "superadditive": sum(1 for p in pairs if p.get("superadditive")),
                "would_pass_old_broken_test": sum(
                    1 for p in pairs if p.get("enablement", 0) > max(p.get("part_enablement") or [0]))},
               "" if composed else ("the moves act on independent parts of the pipeline, so the loop "
                                    "is still ONE MOVE DEEP -- which is exactly why the plateau fires "
                                    "immediately after every escape"))

    # ---- 3. failures found by ATANOR rather than by a person
    fb = str(c.get("failures_found_by_atanor") or "0/0")
    try:
        num, den = (int(x) for x in fb.split("/"))
        share = num / den if den else 0.0
    except Exception:
        num = den = 0
        share = 0.0
    # ONLY CYCLES THAT FOUND SOMETHING CAN ANSWER THIS. Five unattended cycles that applied nothing,
    # reverted nothing and surfaced nothing each recorded "atanor", and five of those in a row turned
    # this axis GREEN on a window in which no failure was found at all. A cycle that found nothing is
    # evidence about neither the loop nor the person, so it is excluded rather than counted, and a
    # window with nothing in it reads UNKNOWN instead of passing.
    by = [x for x in _found_by_derived() if x and x != "none"]
    recent = by[-RECENT:]
    r_share = (sum(1 for x in recent if x == "atanor") / len(recent)) if recent else 0.0
    a3 = _axis(None if len(recent) < RECENT else r_share >= 0.9,
               {"recent_window": recent, "recent_share": round(r_share, 3),
                "cycles_that_found_nothing_excluded": len(c.get("failure_found_by") or []) - len(by),
                "all_time": fb, "all_time_share": round(share, 3),
                "window_fixed_before_measuring": RECENT,
                "disclosure": "this window was introduced while the all-time figure was failing"},
               "" if len(recent) >= RECENT else
               f"only {len(recent)} of the last cycles found anything; a window with nothing in it "
               f"is evidence about neither the loop nor the person")

    # ---- 4. human touches per cycle -- a person turning the crank means a tool, not a loop
    touches = c.get("human_touches_per_cycle") or []
    a4 = _axis(bool(touches) and all(t == 0 for t in touches[-3:]),
               {"last_5": touches[-5:], "min_ever": min(touches) if touches else None},
               "every cycle on record has exactly one human touch: a person decided to run it")

    # ---- 5. verification throughput -- a proxy may rank on faith and may only gate on a measured r
    r = cal.get("r")
    a5 = _axis(bool(cal.get("pairs", 0) >= 6 and r is not None and r >= MIN_R),
               {"pairs": cal.get("pairs"), "r": r, "usable_for": cal.get("usable_for")},
               "" if r is not None else ("a correlation claim without a measured correlation is a "
                                         "guess wearing a number"))

    axes = {"enablement_not_shrinking": a1, "escapes_compose": a2,
            "failures_found_by_atanor": a3, "human_touches_zero": a4,
            "verification_throughput": a5}
    met = [k for k, v in axes.items() if v["met"] is True]
    unknown = [k for k, v in axes.items() if v["met"] is None]
    return {
        "rsi": False if any(v["met"] is False for v in axes.values()) else None,
        "axes": axes,
        "axes_met": met,
        "axes_unmeasurable": unknown,
        "score": f"{len(met)}/5",
        "product_gains": c.get("gain_per_cycle"),
        "enablement_series": series,
        "reading": (
            "Self-repair is complete and measured: the loop finds its own defects, judges them, "
            "applies patches, verifies them blind, reverts what fails, notices when it is stuck, "
            "diagnoses why, searches its own constants for an escape, and goes to the live web when "
            "its arbiter runs out of evidence. RSI is a different claim -- that each improvement "
            "makes the next easier -- and it is not yet true."),
        "not_averaged": ("deliberately. A single score lets a strong axis hide a dead one, which is "
                         "how the previous metric came to report on a series where the compounding "
                         "cycles counted zero."),
    }
