# -*- coding: utf-8 -*-
"""A seconds-long stand-in for the hour-long gate — and the correlation that says whether to trust it.

    from packages.meta_diagnosis.cheap_proxy import proxy_score, calibration
    proxy_score()      # the fast number
    calibration()      # how well it has tracked the expensive gate, on the runs we have

WHY THIS IS A FLOOR AND NOT AN OPTIMISATION. The rate-limiting step in this project is not compute and
not electricity. It is measured: **1.2 hours per B2 arm to test one change.** At that rate the loop
gets a handful of verified cycles a day, and with product gains already halving between patches
(+0.0906 then +0.0385), a handful of cycles buys very little. A search over escape moves is only
possible if evaluating a move is cheap; at an hour a move, the search is theatre.

So the budget to spend is VERIFICATION THROUGHPUT, and a proxy that predicts the expensive gate in
seconds is worth more than faster hardware.

THE PROXY, and why these two signals. Both are already computed by the pipeline and neither needs the
daemon:

    gloss cue_recall on a held-out slice   what the extractor SEES        seconds
    corroborable share                     what would SURVIVE consensus   seconds

The second matters because E5-2 measured what the first alone misses: a change reached the direct
consumer at +5.3% and the consensus-gated one at +1.9%, because rows nothing corroborates never reach
the queue. A proxy built on recall alone would have predicted E5-2 as a pass.

HOW IT MUST BE READ, and this is the part that keeps it honest. A proxy is a claim about correlation,
and a claim about correlation without a measured correlation is a guess wearing a number. `calibration()`
reports the observed pairs -- proxy value against the sealed B2 result, from the E5 runs on record --
and refuses to report an r when there are too few. Three points is not a correlation. Until there are
enough, the proxy RANKS candidates and does not replace the gate: it is allowed to say "try this one
first", never "this one passed".
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAIRS = REPO / "data" / "meta_diagnosis" / "proxy_calibration.jsonl"
MIN_PAIRS_FOR_R = 6

#: THE SLICE THE GATE JUDGES ON. `provisional.try_patch` defaults to holdout_offset=500000, and the
#: first version of this proxy read the SAME 500000. A predictor evaluated on the rows it is predicting
#: is not a predictor -- it was literally half of the gate, recomputed. Any r measured that way would
#: have been high and worth nothing, and it would have been the fifth instrument defect of the day.
GATE_OFFSET = 500000
#: where the proxy reads instead: disjoint from the gate's 40000-row window, so predicting the gate is
#: a claim about generalisation rather than a restatement.
PROXY_OFFSET = 600000


def _recall(offset: int = PROXY_OFFSET, sample: int = 40000) -> float | None:
    out = REPO / "data" / "perception" / "gloss_lane_recall.json"
    try:
        subprocess.run([sys.executable, "scripts/gloss_lane_recall.py",
                        "--sample", str(sample), "--offset", str(offset)],
                       cwd=REPO, capture_output=True, timeout=3600)
        return float(json.loads(out.read_text(encoding="utf-8"))["cue_recall"])
    except Exception:
        return None


def corroborable_share(sample: int = 6000) -> float | None:
    """Of the rows the extractor would assert, what share could a second source confirm?

    The half of the expensive gate that recall cannot see. E5-2 measured the gap directly: +5.3% at
    the direct consumer, +1.9% behind consensus."""
    try:
        from packages.graph_scale.property_extraction import extract
        from packages.self_repair.pattern_proposer import _sample_glosses
        from packages.self_repair.relation_discovery import conceptnet
    except Exception:
        return None
    cn = conceptnet()
    import re

    def norm(s):
        return re.sub(r"[^a-z ]", "", str(s).lower().replace("_", " ")).strip()

    total = corroborable = 0
    for word, gloss in _sample_glosses(sample):
        ents = cn.get(norm(word))
        for _pred, obj in extract(word, gloss) or []:
            total += 1
            if not ents:
                continue
            o = norm(obj)
            if any(o == norm(e.split(":", 1)[1]) or o in norm(e.split(":", 1)[1])
                   for e in ents if ":" in e):
                corroborable += 1
    return round(corroborable / total, 5) if total else None


def proxy_score(*, offset: int = PROXY_OFFSET) -> dict:
    """The fast number, and its parts, so a caller can see which half moved."""
    started = time.time()
    rec = _recall(offset)
    corr = corroborable_share()
    return {"cue_recall": rec, "corroborable_share": corr,
            "proxy": round((rec or 0) * 0.5 + (corr or 0) * 0.5, 5),
            "elapsed_s": round(time.time() - started, 1),
            "note": ("half what the extractor sees, half what would survive consensus -- because "
                     "E5-2 measured that recall alone predicts the wrong arm")}


def record_pair(proxy: float, sealed_b2: int, label: str = "") -> None:
    """One (proxy, expensive-gate) observation. The only thing that can justify trusting the proxy."""
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    with PAIRS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label,
                             "proxy": proxy, "sealed_b2": sealed_b2}, ensure_ascii=False) + "\n")


def calibration() -> dict:
    """How well the proxy has tracked the sealed gate -- and a refusal to say when it cannot know."""
    rows = []
    if PAIRS.exists():
        for line in PAIRS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    # DISTINCT observations, not rows. The first calibration run produced six rows and r=1.0, and those
    # six rows held TWO values: one cue proposed for four different relations gives four IDENTICAL
    # recall deltas, because recall sees the REGEX and never sees the relation label. Six copies of two
    # points is two points, and any two points correlate perfectly. An n that counts duplicates is an n
    # that manufactures its own significance.
    # The standard for what counts as an observation is not decided here either. If someone rewrites
    # this to count rows again, the ledger says why that was defeated and the reason rides along.
    from packages.self_repair.criteria_ledger import in_force
    governing = in_force("n_counts_rows", default="n is the number of rows on file")

    rows = [r for r in rows if r.get("usable", True)]
    seen, distinct = set(), []
    for r in rows:
        k = (r.get("proxy"), r.get("sealed_b2"))
        if k not in seen:
            seen.add(k)
            distinct.append(r)
    duplicates = len(rows) - len(distinct)
    rows = distinct
    n = len(rows)
    if n < MIN_PAIRS_FOR_R:
        return {"pairs": n, "duplicates_discarded": duplicates, "r": None,
                "criterion_in_force": governing["criterion"],
                "usable_for": "RANKING candidates only",
                "why": (f"{n} observation(s); an r needs at least {MIN_PAIRS_FOR_R}. Until then the "
                        f"proxy may say 'try this first' and may never say 'this passed' -- a "
                        f"correlation claim without a measured correlation is a guess wearing a "
                        f"number"),
                "observations": rows}
    xs = [r["proxy"] for r in rows]
    ys = [float(r["sealed_b2"]) for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    r = cov / (vx * vy) if vx and vy else 0.0
    return {"pairs": n, "duplicates_discarded": duplicates, "r": round(r, 4),
            "criterion_in_force": governing["criterion"],
            "usable_for": "ranking, and gating only if r is high and stated with the answer",
            "observations": rows}


def _append(rec: dict) -> None:
    with PAIRS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def calibrate_one(apply_fn, revert_fn, label: str) -> dict:
    """One honest (proxy, gate) observation: measure BOTH slices around the same change.

    The proxy is asked to predict the gate's slice from a DIFFERENT slice, which is the only version of
    this question worth answering. Deltas rather than levels, because the decision the loop makes is
    "will this change help", and a level cannot answer that."""
    pb = _recall(PROXY_OFFSET)
    gb = _recall(GATE_OFFSET)
    token = apply_fn()
    try:
        pa = _recall(PROXY_OFFSET)
        ga = _recall(GATE_OFFSET)
    finally:
        revert_fn(token)
    if None in (pb, gb, pa, ga):
        return {"label": label, "usable": False, "why": "a recall run returned nothing"}
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "label": label,
           "proxy": round(pa - pb, 6), "sealed_b2": round(ga - gb, 6),
           "proxy_slice": PROXY_OFFSET, "gate_slice": GATE_OFFSET, "usable": True}
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    _append(rec)
    return rec
