# -*- coding: utf-8 -*-
"""Perform the escape the diagnosis named — extend the relation vocabulary, and let measurement keep it.

    from packages.self_repair.escape import perform
    r = perform()          # acts on the highest-evidence unacted finding, or explains why not

WHAT CLOSES HERE. `plateau_escape.diagnose()` says which dimension is saturated and, when the
capability already exists, which of its findings nobody acted on. Acting on them was the last thing in
this loop that only a person did. It is mechanisable for exactly one class of escape — the one whose
ingredients the loop already holds:

    the relation NAME        found by relation_discovery against an external vocabulary
    the PATTERN              built by pattern_proposer from the shape of patterns that work
    the INSERTION            done by provisional, which reverts on a bad measurement
    the VERIFICATION         held-out recall, plus agreement with the oracle that named the relation

None of that is invention. It is wiring four organs that each already ran today into one act.

WHY A NEW RELATION NEEDS A DIFFERENT GATE, and this is the substantive part. `relation_fit.judge()`
scores a proposal against the relation's own history, and a relation being ADDED has no history — it
would abstain, correctly, and abstention here would let anything through. So the gate for a brand-new
relation is the external one: the rows it produces must agree with the vocabulary that named it,
better than shuffled pairs do. That is the same base-rate-controlled check that discovered the
relation, applied to what it would actually assert.

WHAT THIS IS NOT. It performs escapes whose PARTS the loop already has. It cannot write a new kind of
proposer, invent a signal nobody measured, or design an organ — the three things a person did today
when the diagnosis said the discriminator or the proposal shape was saturated. Those have no oracle,
and this module does not pretend to reach them. It closes one escape route, and names the ones it
leaves open.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXTRACTOR = "packages/graph_scale/property_extraction.py"
MIN_NET_AGREEMENT = 0.05     # above the shuffled baseline; the same bar discovery had to clear
MIN_PAIRS = 40


def _internal_name(external: str) -> str:
    """ConceptNet's `HasA` in this repo's convention. Mechanical, not a judgement."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", external).lower()


def _pattern_for(cue: str) -> str | None:
    """The candidate pattern for a cue, in the shape the working patterns share."""
    from packages.self_repair.pattern_proposer import pattern_shape
    shape = pattern_shape()
    if not shape:
        return None
    return r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\s+" + shape


def _external_check(cue: str, relation: str) -> dict:
    """Would the rows this cue produces actually be that relation, per the oracle that named it?

    The gate that replaces judge() for a relation with no history. Base-rate controlled, because a
    common relation matches shuffled pairs too — the defect that made discovery's first run report
    IsA."""
    from packages.graph_scale.property_extraction import clean_object
    from packages.self_repair.pattern_proposer import _sample_glosses
    from packages.self_repair.relation_discovery import agreement, null_rate

    rx = re.compile(_pattern_for(cue) or "(?!)", re.I)
    pairs = []
    for word, gloss in _sample_glosses():
        m = rx.search(gloss)
        if m:
            o = clean_object(m.group(1))
            if o:
                pairs.append((word, o))
    checkable, agreed = agreement(pairs, relation)
    raw = (agreed / checkable) if checkable else 0.0
    null = null_rate(pairs, relation)
    return {"pairs": len(pairs), "checkable": checkable, "raw": round(raw, 4),
            "null": round(null, 4), "net": round(max(0.0, raw - null), 4)}


def perform(*, dry_run: bool = False) -> dict:
    """Act on the best unacted relation finding, or say precisely why nothing was done."""
    from packages.self_repair.plateau_escape import diagnose
    from packages.self_repair.provisional import try_patch

    d = diagnose()
    if not d.get("plateaued"):
        return {"acted": False, "why": "not plateaued; there is no escape to perform"}
    findings = d.get("unacted_findings") or []
    if not findings:
        return {"acted": False, "saturated": d.get("saturated"),
                "why": (f"the saturated dimension is {d.get('saturated')!r} and it has no unacted "
                        f"finding to act on. {d.get('next_kind')}"),
                "needs_a_person": True}

    best = max(findings, key=lambda f: (f.get("checkable") or 0, f.get("pairs") or 0))
    external = best["relation"]
    internal = _internal_name(external)
    check = _external_check(best["cue"], external)

    if check["pairs"] < MIN_PAIRS or check["net"] < MIN_NET_AGREEMENT:
        return {"acted": False, "finding": best, "check": check,
                "why": (f"the rows this would assert do not clear the external gate: net agreement "
                        f"{check['net']} over {check['checkable']} checkable "
                        f"(need {MIN_NET_AGREEMENT} and {MIN_PAIRS} pairs)")}

    pattern = _pattern_for(best["cue"])
    line = "    (%r, re.compile(%r, re.I)),\n" % (internal, pattern)
    anchor = '    ("made_of", re.compile('
    if dry_run:
        return {"acted": False, "dry_run": True, "finding": best, "check": check,
                "would_insert": line.strip(), "internal_name": internal}

    r = try_patch(EXTRACTOR, anchor, line + anchor,
                  motivated_by=(f"escape: extend the relation vocabulary with {external} "
                                f"(cue {best['cue']!r}, net agreement {check['net']})"))
    return {"acted": True, "kept": r.get("kept"), "finding": best, "check": check,
            "internal_name": internal, "patch": {k: r[k] for k in
                                                 ("rise", "row_inflation", "outcome", "detail")
                                                 if k in r},
            "note": ("a new relation is judged by the external oracle that named it, because it has "
                     "no history of its own for judge() to score against")}
