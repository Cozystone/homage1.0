# -*- coding: utf-8 -*-
"""One turn of the loop, in one call — measure, propose, judge, hand the survivor to an operator.

    from packages.self_repair.self_cycle import run
    print(run())

WHY THIS IS THIN ON PURPOSE. The three stations already exist and each is tested. What did not exist
was a way to run them as one act: every cycle so far needed a person to call the harness, read its
misses, hand them to the proposer and read the verdicts. That is what `human_touches: 1` in the
improvement-cycle ledger has been counting, and it is the number this file exists to move.

HOW IT DIFFERS FROM `repair_cycle`, which is a real loop and not a duplicate of this one:

    repair_cycle   defects come from ADVISOR journals; patches come from an external model via
                   ask_cli; ATANOR's contribution is judgement and staging.
    self_cycle     defects come from ATANOR's own harnesses; proposals come from a shape abstracted
                   from patterns that already work; no external mind is involved at any step.

Both are legitimate — the Brain-Link doctrine is explicit that an advisor may draft while ATANOR
judges. They are kept apart because their FAILURE MODES differ: one can be wrong because an advisor
was, the other because a measurement was.

WHAT IT WILL NOT DO. It does not apply anything. A surviving proposal is written to the operator queue
with its full evidence, and stops there. Self-modification is operator-gated by the project's
constitution, and a loop that could quietly edit its own extractor is exactly the thing that gate
exists for — the more so because this loop's own judgement station was defeated three times in one
afternoon before it held.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUEUE = REPO / "data" / "self_repair" / "operator_queue.jsonl"



def _missing_relations(survey_result: dict) -> list:
    """For each cue the judge REFUSED, ask whether it means a relation we cannot express.

    A refusal used to be the end of the line. It is now a question: the judge says "these objects fit
    no relation of ours decisively", and the honest follow-up is whether they fit one we do not have.
    Checked against an external vocabulary, controlled for base rate, so a common relation cannot win
    by being common."""
    import re
    from packages.graph_scale.property_extraction import clean_object
    from packages.self_repair.pattern_proposer import _sample_glosses, pattern_shape
    from packages.self_repair.relation_discovery import discover

    refused = {c["cue"] for c in (survey_result.get("refused_detail") or [])}
    if not refused:
        return []
    shape = pattern_shape()
    if not shape:
        return []
    rows = _sample_glosses()
    out = []
    for cue in sorted(refused):
        lead = r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\s+"
        try:
            rx = re.compile(lead + shape, re.I)
        except re.error:
            continue
        pairs = []
        for w, g in rows:
            m = rx.search(g)
            if m:
                o = clean_object(m.group(1))
                if o:
                    pairs.append((w, o))
        d = discover(cue, pairs)
        if d.get("verdict") == "missing_relation":
            out.append({"cue": cue, "relation": d["missing_relation"], "pairs": len(pairs),
                        "evidence": d["why"], "checkable": list(d["best_external"].values())[0]["checkable"]})
    return out


def run(*, top_cues: int = 8, record_cycle: bool = False) -> dict:
    """Measure, propose, judge. Returns what survived and what was refused, and queues the survivors.

    `record_cycle` is off by default: writing to the improvement-cycle ledger is a claim about
    progress, and a cycle that merely ran is not progress. The caller decides."""
    started = time.time()
    from packages.self_repair.pattern_proposer import survey
    from packages.self_repair.self_measured import emit, scan

    defects = scan()
    for d in defects:
        emit(d)

    result = survey(top_cues=top_cues)
    survivors = result.get("accepted_detail") or []

    # STATION 3b: a cue the judge refuses may be refused because it means something the vocabulary
    # cannot say. Asking that question is what stopped the loop being one shape wide -- it proposed
    # 24 and queued 0, correctly, because its largest missed cues are relations ATANOR does not have.
    missing = _missing_relations(result)
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a", encoding="utf-8") as fh:
        for s in survivors:
            fh.write(json.dumps({**s, "queued_at": time.time(), "state": "awaiting_operator",
                                 "applied": False}, ensure_ascii=False) + "\n")

    return {
        "defects_found": len(defects),
        "defect_keys": [d.key for d in defects],
        "proposed": result.get("proposed", 0),
        "refused": result.get("proposed", 0) - len(survivors),
        "queued_for_operator": len(survivors),
        "missing_relations": missing,
        "survivors": [{"cue": s["cue"], "relation": s["relation"], "fires": s["fired"]}
                      for s in survivors],
        "applied": 0,
        "elapsed_s": round(time.time() - started, 1),
        "boundary": ("proposals only. Nothing here edits code; self-modification is operator-gated, "
                     "and this loop's own judgement station failed three times before it held"),
    }


def pending() -> list[dict]:
    """What is waiting for an operator, oldest first."""
    if not QUEUE.exists():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("applied"):
                out.append(r)
    return out
