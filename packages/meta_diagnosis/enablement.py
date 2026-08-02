# -*- coding: utf-8 -*-
"""Score a capacity cycle by what it UNLOCKED, because gain scores it zero by construction.

    from packages.meta_diagnosis.enablement import snapshot, enablement_since
    before = snapshot()          # what survives the gates right now
    ... make a capacity change ...
    enablement_since(before)     # what newly survives, and what that is worth

THE DEFECT THIS REPAIRS, visible in the ledger rather than argued: every capacity cycle recorded so
far scores exactly 0.0000.

    loop-stations-1-2-3                capacity  0.0000
    reachability-census                capacity  0.0000
    escape performed: has_a added      capacity  0.0000
    oracle expansion                   capacity  0.0000

They score zero BY CONSTRUCTION. `gain` is a product metric, and a cycle that improves the improver
moves no product metric on the day it lands. And capacity cycles are the only kind that compounds --
the product cycles accumulate, the second patch worth less than half the first. So `gains_holding`
averages a series in which the compounding cycles contribute nothing, and cannot detect the thing it
exists to detect. The instrument, not the loop, is why RSI reads false.

WHAT COMPOUNDING LOOKED LIKE WHEN IT HAPPENED. Once, today, unrecorded. Fixing within-cluster
discrimination -- a capacity cycle, scored 0.0 -- took the proposer from ZERO survivors to three
proposable cues, two of which became patches that survived blind measurement at +0.0906 and +0.0385.
That cycle enabled roughly 0.13 of product gain that was impossible before it.

ENABLEMENT IS THAT NUMBER. Snapshot what survives the gates, make the change, snapshot again: what
newly survives is what the change unlocked. It is measured the same way a product gain is -- by
running the thing and looking -- so it inherits the same free oracle rather than needing a new one.

WHY THIS IS NOT A METRIC BUILT TO PASS. It can be zero, and usually will be: most capacity work
unlocks nothing immediately, and saying so is the point. A capacity cycle that unlocks nothing is
recorded as unlocking nothing, which is exactly what `gain` was already doing -- the difference is
that this one CAN move, so a zero from it is evidence rather than an artefact.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "meta_diagnosis" / "enablement.jsonl"


def _survivor_keys(top_cues: int = 12) -> set:
    """What currently clears every gate, as (cue, relation) pairs.

    The proposer's own output, not a reimplementation of it -- so enablement measures the real
    pipeline and moves when the real pipeline moves."""
    from packages.self_repair.pattern_proposer import survey
    r = survey(top_cues=top_cues)
    return {(c["cue"], c["relation"]) for c in (r.get("accepted_detail") or [])}


def _relation_keys() -> set:
    """Missing relations the discovery station can currently name."""
    try:
        from packages.self_repair.self_cycle import _missing_relations
        from packages.self_repair.pattern_proposer import survey
        return {(m["cue"], m["relation"]) for m in _missing_relations(survey(top_cues=12))}
    except Exception:
        return set()


def snapshot(*, top_cues: int = 12, label: str = "") -> dict:
    """What the loop can currently do, in the only terms that matter: what clears the gates."""
    return {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "survivors": sorted(_survivor_keys(top_cues)),
        "missing_relations": sorted(_relation_keys()),
    }


def enablement_since(before: dict, *, top_cues: int = 12, label: str = "",
                     record: bool = True) -> dict:
    """What became possible that was not possible before.

    `newly_possible` is the count that matters; `lost` is reported alongside because a capacity change
    that unlocks two things and breaks three has not enabled anything, and a one-sided metric would
    hide that."""
    after = snapshot(top_cues=top_cues, label=label)
    b_s, a_s = {tuple(x) for x in before.get("survivors", [])}, {tuple(x) for x in after["survivors"]}
    b_r = {tuple(x) for x in before.get("missing_relations", [])}
    a_r = {tuple(x) for x in after["missing_relations"]}

    gained, lost = sorted(a_s - b_s), sorted(b_s - a_s)
    rel_gained, rel_lost = sorted(a_r - b_r), sorted(b_r - a_r)
    rec = {
        "at": after["at"], "label": label,
        "survivors_before": len(b_s), "survivors_after": len(a_s),
        "newly_possible": [list(x) for x in gained],
        "no_longer_possible": [list(x) for x in lost],
        "relations_newly_nameable": [list(x) for x in rel_gained],
        "relations_no_longer_nameable": [list(x) for x in rel_lost],
        "enablement": len(gained) - len(lost) + len(rel_gained) - len(rel_lost),
        "reading": ("a capacity cycle is worth what it unlocks; unlocking nothing is a real answer "
                    "and is recorded as one"),
    }
    if record:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def trajectory() -> dict:
    """Is enablement per capacity cycle holding up? This is the RSI question, as a series."""
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    if not rows:
        return {"capacity_cycles_scored": 0, "note": "nothing scored yet"}
    series = [r["enablement"] for r in rows]
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    return {
        "capacity_cycles_scored": len(rows),
        "enablement_per_cycle": series,
        "enablement_deltas": deltas,
        "holding": all(d >= 0 for d in deltas[-3:]) if deltas else None,
        "total_unlocked": sum(series),
        "labels": [r.get("label") for r in rows],
        "reading": ("RSI is enablement not shrinking across capacity cycles. Product gain accumulates; "
                    "only enablement compounds."),
    }
