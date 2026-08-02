# -*- coding: utf-8 -*-
"""Turn what ATANOR noticed about itself DURING USE into the deficit signals its drive already reads.

The owner's shape (2026-07-28): a person carrying boxes discovers a limit, and the discovery -- not
a schedule -- generates a standing commitment to train. Four parts matter, and the fourth is the
one usually missed:

    1. the trigger fires during ORDINARY activity, not during a self-test;
    2. it is felt as insufficiency;
    3. it becomes a commitment that PERSISTS and is returned to;
    4. the training is NOT the original task -- you do not get stronger by carrying more boxes.

ATANOR already has (1) and (2) in several ledgers, and (3) in `autonomy_kernel.goals`, which grows
a goal from a deficit seen ACROSS cycles ("a one-off is noise") and tracks improving/stalled/
regressing against a real metric. What was missing was the wire between them:
`WorldModelSnapshot.contradictions` is read by `deficit.compute_deficit`, but the summary dict that
fills it is built by `selfhood_control.bridges` from sources that never heard of the conflict
ledger. So the limits were felt and recorded, and the drive never saw them.

On (4): the remediation here is deliberately different from the task that exposed the limit.
Answering "what country is Athens in?" again cannot fix a merged node -- the fix is acquisition
against an external source. Carrying more boxes is not training.

HONEST BOUNDARY. This produces a control signal, exactly as `deficit.py` says of itself: "a deficit
signal is a control signal, not an emotion and not evidence of consciousness." It changes what the
system attends to. It is not a claim that anything is felt.
"""
from __future__ import annotations

from typing import Any


def limits_as_contradictions(min_hits: int = 1, limit: int = 20) -> list[dict[str, Any]]:
    """Standing knowledge conflicts, in the shape `WorldModelSnapshot.contradictions` carries.

    Severity rises with how often the conflict actually BLOCKED an answer, not with how large it
    is: a node tripped over three times matters more than a bigger one nobody asks about. That is
    the same ordering the conflict ledger uses, carried through rather than re-derived."""
    try:
        from packages.knowledge_repair.conflict_ledger import standing_conflicts
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for c in standing_conflicts(limit=limit):
        if c.hits < min_hits:
            continue
        # bounded: many hits should saturate, not dominate every other signal in the snapshot
        severity = min(1.0, 0.3 + 0.15 * c.hits)
        out.append({
            "kind": "merged_referent",
            "subject": c.subject,
            "predicate": c.predicate,
            "competing_values": len(c.values),
            "hits": c.hits,
            "severity": round(severity, 4),
            "question": c.as_question(),
            "source": "knowledge_repair.conflict_ledger",
        })
    return out


def limits_as_unresolved(limit: int = 20) -> list[str]:
    """Questions ATANOR could not even FORM, in the shape `unresolved_questions` carries.

    Distinct from a contradiction on purpose: a contradiction is knowledge that disagrees with
    itself, an unread question is knowledge that has no shape to disagree in. They call for
    different training -- acquisition versus widening the composer -- which is exactly why they
    must not be merged into one bucket."""
    try:
        from packages.flywheel.logger import unread_curriculum
    except Exception:
        return []
    return [f"{r['reason']} (blocked {r['count']}x, e.g. {r['example'][:80]})"
            for r in unread_curriculum(limit=limit)]


def merge_into_world_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Add self-noticed limits to a world-model summary WITHOUT dropping what is already there.

    Additive by contract: a caller that already supplies contradictions keeps them, so wiring this
    in can only widen what the drive sees. Returns a new dict; the input is not mutated."""
    merged = dict(summary or {})
    merged["contradictions"] = list(merged.get("contradictions") or []) + limits_as_contradictions()
    merged["unresolved_questions"] = (list(merged.get("unresolved_questions") or [])
                                      + limits_as_unresolved())
    return merged
