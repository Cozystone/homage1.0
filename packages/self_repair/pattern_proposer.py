# -*- coding: utf-8 -*-
"""Station 3: propose the change, and let measurement decide which proposal survives.

    from packages.self_repair.pattern_proposer import propose, evaluate
    for cand in propose():            # from the harness's own misses
        print(evaluate(cand))         # three gates, none of them an opinion

WHERE THE PROPOSALS COME FROM, and why this is not me inventing pattern shapes. The extractor's seven
working patterns all share one form:

    \\b<CUE>\\s+(<object span>)(?=<terminators>)

That form is ABSTRACTED from the patterns that already work -- anti-unification over a working set,
not a template someone typed. A candidate is that shape instantiated with a cue phrase the gloss
harness measured as missing. So the proposal step contributes no new judgement at all: the shape comes
from what works, the cue comes from what fails, and everything after is measurement.

WHICH RELATION A NEW CUE MEANS IS NOT DECIDED HERE EITHER. `designed to`, `able to`, `serves to`,
`a vessel` -- each is tried against EVERY relation, and `relation_fit` says which assignment produces
objects that relation actually takes. Assigning it myself is exactly the step that produced the
`consisting of` mistake, where the obvious mapping was the wrong one.

THE THREE GATES a candidate must clear, all automatic:

    1. it must FIRE          a pattern that matches nothing is not an improvement
    2. relation_fit accepts  the objects must look like ones the relation already takes
    3. recall must rise      on the harness's own deterministic slice, without agreement falling

A candidate that clears all three is a proposal to a human, not an applied patch. Self-modification
stays operator-gated; what this closes is the generate half of generate-and-verify.

WHAT THIS IS HONESTLY NOT. The proposal space is one shape wide. It can suggest "this cue phrase, this
relation", and it cannot invent a structurally new kind of pattern, restructure the extractor, or
notice that a whole relation is missing from the vocabulary. It is the narrowest station in the loop,
and its narrowness is the reason it can be trusted to run unattended.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS_REPORT = REPO / "data" / "perception" / "gloss_lane_recall.json"
GLOSSES = REPO / "data" / "graph_scale" / "primary_gloss.jsonl"

#: the relations the extractor knows. Read from its own table rather than listed here, so a relation
#: added upstream becomes proposable without touching this file.
def known_relations() -> tuple:
    from packages.graph_scale.property_extraction import PATTERNS
    return tuple(dict.fromkeys(pred for pred, _pat in PATTERNS))


def pattern_shape() -> str:
    """The form every working pattern shares, abstracted from the working set.

    Read off `PATTERNS` rather than written down: the object span and the terminator set are lifted
    from a pattern that already earns its place, so a candidate inherits whatever those have been
    tuned to and cannot drift from them."""
    from packages.graph_scale.property_extraction import PATTERNS
    src = PATTERNS[0][1].pattern
    m = re.search(r"(\(\[[^)]*?\]\{[\d,]+\}\?\))(\(\?=.*)$", src, re.S)
    if not m:                                     # shape changed upstream -- refuse to guess one
        return ""
    return m.group(1) + m.group(2)


@dataclass
class Candidate:
    cue: str
    relation: str
    regex: str
    misses_behind_it: int = 0
    fired: int = 0
    objects: list = field(default_factory=list)
    verdict: str = ""
    accepted: bool = False

    def as_dict(self) -> dict:
        return {"cue": self.cue, "relation": self.relation, "regex": self.regex,
                "misses_behind_it": self.misses_behind_it, "fired": self.fired,
                "objects": self.objects[:8], "verdict": self.verdict, "accepted": self.accepted}


def already_covered(cue: str) -> bool:
    """Does the extractor ALREADY match this cue? Found by running the loop, not by reading it.

    The first real provisional patch proposed `used in -> used_for`, the strongest signal in the queue
    (96% familiar, margin 63%, instance agreement 95%). It was applied, measured on a held-out slice,
    scored a rise of EXACTLY ZERO, and reverted. The reason: pattern [0] of the extractor is
    `\\bused\\s+(?:for|in)\\s+...` — the cue was already there, and the proposal was a duplicate.

    The mistake was in reading the miss ranking. "This cue appeared and nothing was emitted" has two
    causes, and the proposer assumed the wrong one:

        (a) the extractor has no pattern for the cue        <- what was assumed
        (b) the pattern fired and clean_object refused the object   <- what was actually happening

    All three queued proposals were `used_*` cues, all three already in the table. Checking is cheap:
    run the existing patterns against a probe sentence built from the cue and see whether anything
    fires."""
    from packages.graph_scale.property_extraction import PATTERNS
    probe = f"a thing {cue} something ordinary here."
    return any(rx.search(probe) for _pred, rx in PATTERNS)


def propose(top_cues: int = 6) -> list[Candidate]:
    """One candidate per (missed cue x relation). The cross product is deliberate -- deciding the
    relation is measurement's job, not the proposer's."""
    if not HARNESS_REPORT.exists():
        return []
    report = json.loads(HARNESS_REPORT.read_text(encoding="utf-8"))
    shape = pattern_shape()
    if not shape:
        return []
    out: list[Candidate] = []
    for cue, n in (report.get("top_missed_cues") or [])[:top_cues]:
        cue = str(cue).strip().lower()
        if not cue or len(cue) < 4:
            continue
        if already_covered(cue):
            continue
        lead = r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\s+"
        for rel in known_relations():
            out.append(Candidate(cue=cue, relation=rel, regex=lead + shape,
                                 misses_behind_it=int(n)))
    return out


def _sample_glosses(n: int = 40000) -> list[tuple[str, str]]:
    rows = []
    with GLOSSES.open(encoding="utf-8") as fh:
        for line in fh:
            if len(rows) >= n:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            w, g = str(r.get("word", "")).strip(), str(r.get("gloss", "")).strip()
            if w and g:
                rows.append((w, g))
    return rows


#: our relation names in the external vocabulary, for the veto check
_EXTERNAL = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf",
             "has_a": "HasA", "part_of": "PartOf"}


def evaluate(cand: Candidate, glosses=None, min_fire: int = 15) -> Candidate:
    """Run the candidate over real glosses and let the gates speak.

    The objects are collected through the extractor's own `clean_object`, so a candidate is judged on
    what would actually be ASSERTED -- not on what its regex captures before normalisation, which is
    a different and more flattering thing."""
    from packages.graph_scale.property_extraction import clean_object
    from packages.self_repair.relation_fit import judge

    try:
        rx = re.compile(cand.regex, re.I)
    except re.error as exc:
        cand.verdict = f"not a valid pattern: {exc}"
        return cand
    rows = glosses if glosses is not None else _sample_glosses()
    objs: list[str] = []
    pairs: list[tuple] = []
    for word, gloss in rows:
        m = rx.search(gloss)
        if not m:
            continue
        o = clean_object(m.group(1))
        if o:
            objs.append(o)
            pairs.append((word, o))
    cand.fired = len(objs)
    cand.objects = sorted(set(objs))[:40]

    if cand.fired < min_fire:
        cand.verdict = f"fires on only {cand.fired} glosses; too thin to judge or to be worth adding"
        return cand
    v = judge(cand.relation, objs)
    cand.accepted = bool(v.accept)
    cand.verdict = f"fires {cand.fired}x | {v.reason}"

    # THE ARBITER GETS A VETO, not just a say when the judge refuses. judge() scores against OUR OWN
    # extracted rows, so it inherits whatever confusion is already in them; the external vocabulary is
    # the only opinion here that did not come from us. It used to be consulted solely for refused cues
    # (to hunt a missing relation), which left the one direction that matters unguarded: a proposal the
    # judge ACCEPTS and an independent source contradicts.
    #
    # The case that exposed it: `intended to -> capable_of` was accepted on profile similarity, and
    # with the oracle expanded 30x the same pairs score ZERO agreement over 32 checkable. Silence is
    # not a veto -- too few checkable pairs leaves the judge's verdict standing -- but evidence is.
    if cand.accepted and pairs:
        try:
            from packages.self_repair.relation_discovery import agreement, null_rate
            ext = _EXTERNAL.get(cand.relation)
            if ext:
                checkable, agreed = agreement(pairs, ext)
                if checkable >= 20:
                    net = (agreed / checkable) - null_rate(pairs, ext)
                    if net <= 0.01:
                        cand.accepted = False
                        cand.verdict += (f" | VETOED by the external oracle: {ext} agreement "
                                         f"{net:+.3f} over {checkable} checkable pairs, so an "
                                         f"independent source sees no such relation here")
        except Exception:
            pass

    # R -- DIACHRONIC NORMATIVE ACCOUNTABILITY. If this system already tried this exact proposal and
    # its own held-out gate said no, proposing it again is not new information; it is going back on a
    # finding. That does not make it forbidden. It makes it EXPENSIVE: the candidate has to show more
    # evidence than it did when it was wrong.
    #
    # The distinction from every other check in this file is deliberate. The external-oracle veto above
    # is a WALL -- it sets accepted False and nothing carries forward. This is FRICTION: it is possible
    # to proceed, and proceeding costs. A constraint that cannot be violated teaches nothing, because
    # nothing was ever at stake in respecting it.
    try:
        from packages.self_repair.normative_accountability import friction, record_episode
        f = friction(cand.cue, cand.relation)
        if f["conflicts"]:
            need = f["extra_firings_required"]
            honoured = cand.fired < need
            if honoured and cand.accepted:
                cand.accepted = False
                cand.verdict += (f" | HELD TO A PAST FINDING: this system tried {cand.cue} -> "
                                 f"{cand.relation} before and reverted it, so it needs {need} firings "
                                 f"rather than the usual bar and has {cand.fired}")
            record_episode(cue=cand.cue, relation=cand.relation, conflicts=f["conflicts"],
                           honoured=honoured, fired=cand.fired, required=need,
                           basis=f.get("basis", ""),
                           detail=f"fired {cand.fired} against a required {need}; "
                                  f"{'held' if honoured else 'cleared the higher bar'}")
    except Exception as exc:
        # NOT SWALLOWED. The first version of this block ended in `except Exception: pass`, and a
        # keyword mismatch -- `conflicted=` defined against `conflicts=` passed -- meant NO episode was
        # ever recorded while `holds()` calmly reported zero. That is the fifth time in one day a
        # defensive catch turned a defect into a quiet zero. R must not be able to fail silently: an
        # accountability mechanism that cannot report its own breakage is decorative by construction.
        cand.verdict += f" | R CHECK FAILED: {type(exc).__name__}: {exc}"
    return cand


def survey(top_cues: int = 6, glosses=None) -> dict:
    """Every proposal, evaluated. Reports what was refused as loudly as what passed -- a proposer
    that only surfaced its successes would hide the judgement doing the work."""
    rows = glosses if glosses is not None else _sample_glosses()
    cands = [evaluate(c, rows) for c in propose(top_cues)]
    passed = [c for c in cands if c.accepted]
    return {
        "proposed": len(cands),
        "fired_enough": sum(1 for c in cands if c.fired >= 15),
        "accepted": len(passed),
        "accepted_detail": [c.as_dict() for c in passed],
        "refused_detail": [c.as_dict() for c in cands if c.fired >= 15 and not c.accepted][:12],
        "note": ("accepted means the objects fit the relation's measured profile. It is a proposal "
                 "for an operator, never an applied patch -- self-modification stays gated."),
    }
